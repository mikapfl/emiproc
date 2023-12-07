"""Function for doing speciation.

The function speciate_inventory() is the main function.
Other functions are hardcoded for several substances.
"""
from __future__ import annotations

from os import PathLike
from typing import TYPE_CHECKING, Any

import pandas as pd
import xarray as xr
import numpy as np

from emiproc import deprecated
from emiproc.utilities import get_country_mask

if TYPE_CHECKING:
    from emiproc.inventories import Category, CatSub, Inventory


def read_speciation_table(path: PathLike, drop_zeros: bool = False) -> xr.DataArray:
    """Read a speciation table from a file.

    Format of the file:

    ```
    # Any comment line starting with # is ignored
    # The first line is the header, it contains optional information
    # to specify speciation factors for each category.
    category,country,substance0,substance1,substance2, ...
    cat0,c0,0.5,0.2,0.1, ...
    cat1,c0,0.3,0.5,0.0, ...
    cat0,c1,0.2,0.3,0.5, ...
    ...
    ```


    The table can contain optional dimensions:
        - country : must follow the ISO3 naming convention
            In case cells belong to no country and have emissions, you will
            need to set a default value for the speciation ratios.
            This can be done by adding a row with the country set to `-99`.
        - category
        - type : Whether applies to 'gridded' or 'shapped'
        - year

    Ratios are the fraction of the weight of the speciated substance.
    As emissions are given in mass/unit of time, the sum of the ratios
    for a given speciiation must be 1.

    :arg path: The path of the speciation table.
    :arg drop_zeros: Whether to drop the speciation ratios that sum to 0.

    :returns: The speciation ratios.
        The speciation ratios are the weight fraction conversion from the
        speciated substance.

    """
    df = pd.read_csv(path, comment="#")

    # Reserved columns
    columns_types = {
        "category": str,
        "country": str,
        "type": str,
        "year": int,
    }

    new_substances = [col for col in df.columns if col not in columns_types.keys()]

    # Get the ratios data
    ratios = df[new_substances].to_numpy()

    da = xr.DataArray(
        ratios,
        dims=["speciation", "substance"],
        coords={
            "speciation": df.index,
            "substance": new_substances,
        }
        | {
            # Add the optional dimensions that describe the speciation
            k: ("speciation", df[k].to_numpy().astype(t))
            for k, t in columns_types.items()
            if k in df.columns
        },
    )

    if drop_zeros:
        mask_zero = da.sum("substance") == 0
        da = da[~mask_zero]

    # Check that all the speciation ratios sum to 1
    mask_close = np.isclose(da.sum("substance"), 1.0)
    if not mask_close.all():
        raise ValueError(
            "The speciation ratios must sum to 1, but the following rows don't:"
            f" {da[~mask_close]}"
        )

    return da


def speciate(
    inv: Inventory,
    substance: str,
    speciation_ratios: xr.DataArray,
    drop: bool = True,
    country_mask_kwargs: dict[str, Any] = {},
) -> Inventory:
    """Speciate a substance in an inventory.

    :arg inv: The inventory to speciate.
    :arg substance: The substance to speciate.
    :arg speciation_ratios: The speciation ratios. See :py:func:`read_speciation_table`.
    :arg drop: Whether to drop the speciated substance.
    :arg country_mask_kwargs: If the speciation ratios depend on the country,
        this function is used to pass optional arguments to
        :py:func:`emiproc.utilities.get_country_mask`.


    """
    new_inv = inv.copy()

    if "year" in speciation_ratios.coords:
        if inv.year is None:
            raise ValueError(
                f"The inventory {inv} does not have a year, but the speciation ratios"
                f" {speciation_ratios} do."
            )
        # Get the speciation ratios for the year of the inventory
        speciation_ratios = speciation_ratios.sel(year=inv.year)

    if "country" in speciation_ratios.coords:
        countries_fractions: xr.DataArray = get_country_mask(
            new_inv.grid, return_fractions=True, **country_mask_kwargs
        )

    for cat, sub in inv._gdf_columns:
        if sub != substance:
            continue
        # Check that the speciation ratios are defined for this category
        if "category" in speciation_ratios.coords:
            da_ratios = speciation_ratios.loc[speciation_ratios["category"] == cat]
        else:
            da_ratios = speciation_ratios

        if "type" in speciation_ratios.coords:
            da_ratios = da_ratios.loc[da_ratios["type"] == "gridded"]

        if da_ratios["speciation"].size == 0:
            raise ValueError(
                f"The speciation ratios for {cat} and {substance} is not defined."
            )

        if "country" in speciation_ratios.coords:
            # Calculate the ratio at each cell
            # Make the dim on country instead of speciation
            da_ratios_country = da_ratios.set_index(speciation="country").rename(
                {"speciation": "country"}
            )
            da_ratios_cells = countries_fractions.dot(
                da_ratios_country, dims=["country"]
            )
            # First check that where the sum is 0, the total emissions are 0
            mask_zero_ratios = da_ratios_cells.sum("substance") == 0
            mask_zero_emissions = inv.gdf[(cat, substance)] == 0
            mask_problem = mask_zero_ratios & ~mask_zero_emissions
            missing_value = (
                None
                if "-99" not in da_ratios_country.coords["country"].values
                else da_ratios_country.sel(country="-99")
            )
            if mask_problem.any():
                if missing_value is None:
                    raise ValueError(
                        f"The speciation ratios for {cat} and {substance} is not"
                        " defined for the following cells that have emission values :"
                        f" {da_ratios_cells[mask_problem]}"
                    )
                # Set the missing value
                da_ratios_cells = da_ratios_cells.where(
                    ~mask_problem, other=missing_value
                )
            # Put ones where the sum is 0 to avoid later division by 0
            da_ratios_cells = da_ratios_cells.where(~mask_zero_ratios, other=1.0)
            # Correct cells to ensure that the sum is 1
            da_ratios_cells = da_ratios_cells / da_ratios_cells.sum("substance")

            da_ratios = da_ratios_cells

        else:
            # No country, just speciate every cell the same way
            if da_ratios["speciation"].size > 1:
                raise ValueError(
                    f"The speciation ratios for {cat} and {substance} is not unique:"
                    f" {da_ratios=}."
                )
        # Speciate the gdf
        for new_sub in da_ratios["substance"].values:
            # Simply get the single value
            ratios = da_ratios.sel(substance=new_sub).values
            # Should not happen, but just in case
            if (cat, new_sub) in inv._gdf_columns:
                raise KeyError(f"{cat}/{new_sub} already in the gdf of {inv}")
            new_inv.gdf[(cat, new_sub)] = inv.gdf[(cat, substance)] * ratios
        if drop:
            # Drop the speciated substance
            new_inv.gdf.drop(columns=[(cat, substance)], inplace=True)

    # Now for the gdfs
    for cat in inv.gdfs.keys():
        if substance not in inv.gdfs[cat].columns:
            continue
            # Check that the speciation ratios are defined for this category
        if "category" in speciation_ratios.coords:
            da_ratios = speciation_ratios.loc[speciation_ratios["category"] == cat]
        else:
            da_ratios = speciation_ratios

        if "type" in speciation_ratios.coords:
            da_ratios = da_ratios.loc[da_ratios["type"] == "shapped"]

        if da_ratios["speciation"].size == 0:
            raise ValueError(
                f"The speciation ratios for {cat} and {substance} is not defined for"
                " shapped emissions."
            )
        if da_ratios["speciation"].size > 1:
            raise ValueError(
                f"The speciation ratios for {cat} and {substance} is not unique"
                f" {da_ratios=}."
            )

        # Speciate the gdf
        for new_sub in da_ratios["substance"].values:
            speciation_ratio = da_ratios.sel(substance=new_sub).values
            new_inv.gdfs[cat][new_sub] = inv.gdfs[cat][substance] * speciation_ratio
        if drop:
            new_inv.gdfs[cat].drop(columns=[substance], inplace=True)

    # TODO profiles

    new_inv.history.append(f"Speciated {substance} to {da_ratios['substance'].values}.")

    return new_inv


@deprecated(msg="Use speciate instead.")
def speciate_inventory(
    inv: Inventory,
    speciation_dict: dict[CatSub, dict[CatSub, float]],
    drop: bool = True,
) -> Inventory:
    """Speciate an inventory.

    Speciation is splitting one substance into several substances.
    For example NOx can be split into NO and NO2.
    Replaces the current category/substance with the new one.

    :arg inv: The inventory to speciate.
    :arg speciation_dict: A dict with the speciation rules.
        The keys are the category/substance to speciate.
        The values is a dict mapping new category/substance and the fraction
        of the orignal substance to be specified.
        Ratio is the weight fraction conversion from the speciated substance.
        Note that the ratio don't need to sum to 1, depending on the
        chemical parameters.
    :arg drop: Whether to drop the speciated category/substance.

    :returns: The speciated inventory.
    """
    new_inv = inv.copy()

    for cat_sub, new_species in speciation_dict.items():
        cat, sub = cat_sub
        # Check the there is a substance to speciate
        if cat_sub not in inv._gdf_columns and (
            cat not in inv.gdfs or sub not in inv.gdfs[cat]
        ):
            raise KeyError(f"Cannot speciate: {cat_sub} not in {inv}")

        # Speciate the gdf
        if cat_sub in inv._gdf_columns:
            for new_cat_sub, speciation_ratio in new_species.items():
                # if the new cat/sub is already in the gdf raise an error
                if new_cat_sub in inv._gdf_columns:
                    raise KeyError(f"{new_cat_sub} already in the gdf of {inv}")
                new_inv.gdf[new_cat_sub] = inv.gdf[cat_sub] * speciation_ratio
            if drop:
                new_inv.gdf.drop(columns=cat_sub, inplace=True)
        # Speciate the gdfs
        if cat in inv.gdfs and sub in inv.gdfs[cat].columns:
            for new_cat_sub, speciation_ratio in new_species.items():
                new_cat, new_sub = new_cat_sub
                # if the new cat/sub is already in the gdf raise an error
                if new_cat in inv.gdfs and new_sub in inv.gdfs[new_cat].columns:
                    raise KeyError(
                        f"Cannot speciate: {new_cat_sub} already in the gdfs of {inv}"
                    )
                new_inv.gdfs[new_cat][new_sub] = inv.gdfs[cat][sub] * speciation_ratio
            if drop:
                new_inv.gdfs[cat].drop(columns=sub, inplace=True)

    new_inv.history.append(f"Speciated with {speciation_dict}.")

    return new_inv


def speciate_nox(
    inv: Inventory,
    NOX_TO_NO2: float | dict[Category, float] = 0.18,
    drop: bool = True,
) -> Inventory:
    """Speciate NOx into NO and NO2.

    :arg inv: The inventory to speciate.
    :arg drop: Whether to drop the speciated category/substance.
    :arg NOX_TO_NO2: The fraction of NOx that is speciated to NO2.
        It is possible to use a dict with a different fraction for each category.

        .. note::

            Depending on the sector, this value can vary.

            For most emission sources, the fraction of NO is closer to 95%,
            only for traffic a fraction of 82% may be applied.
            The reason is that oxidation catalysts in diesel engines partly
            oxidize NO to NO2 before it is emitted through the tailpipe.
            In the first decade of 2000,
            the fraction of NO gradually decreased from 95% to about 80%.

            See more:

            * https://www.empa.ch/documents/56101/246436/Trend+NO2+Immissionen+Stadt+2022/ddba8b88-c599-4ed4-8b94-cc24670be683
            * https://www.zh.ch/de/umwelt-tiere/luft-strahlung/luftschadstoffquellen/emissionen-verkehr/abgasmessungen-rsd.html



    :returns: The speciated inventory.

    """
    MOLAR_MASS_NO2 = 46.0
    MOLAR_MASS_NO = 30.0
    MM_RATIO = MOLAR_MASS_NO / MOLAR_MASS_NO2

    if isinstance(NOX_TO_NO2, dict):
        speciation_dict = {
            (cat, "NOx"): {
                (cat, "NO"): (1.0 - ratio) * MM_RATIO,
                (cat, "NO2"): ratio,
            }
            for cat, ratio in NOX_TO_NO2.items()
        }
    elif isinstance(NOX_TO_NO2, float):
        # Make sure the fraction is between 0 and 1
        if NOX_TO_NO2 < 0 or NOX_TO_NO2 > 1:
            raise ValueError(f"NOX_TO_NO2 must be between 0 and 1, not {NOX_TO_NO2}.")
        # Aplly the same fraction to all categories
        speciation_dict = {
            (cat, "NOx"): {
                (cat, "NO"): (1.0 - NOX_TO_NO2) * MM_RATIO,
                (cat, "NO2"): NOX_TO_NO2,
            }
            for cat in inv.categories
            if (cat, "NOx") in inv._gdf_columns
            or (cat in inv.gdfs and "NOx" in inv.gdfs[cat].columns)
        }
    else:
        raise TypeError(f"NOX_TO_NO2 must be a float or dict, not {type(NOX_TO_NO2)}.")

    return speciate_inventory(inv, speciation_dict, drop=drop)
