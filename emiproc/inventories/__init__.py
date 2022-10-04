"""Inventories of emissions."""
from __future__ import annotations
from enum import Enum, auto
from os import PathLike
from pathlib import Path
from typing import NewType
from emiproc.grids import LV95, Grid, SwissGrid
from emiproc.regrid import get_weights_mapping, weights_remap
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point
import numpy as np
import rasterio

#Represent a substance that is emitted and can be present in a dataset.
Substance = NewType('Substance', str)


class Inventory:
    """Base class for inventories.

    :attr name: The name of the inventory. This is going to be used
        for adding metadata to the output files, and also for the reggridding
        weights files.
    :attr grid: The grid on which the inventory is.
    :attr substances: The :py:class:`Substance` present in this inventory.
    :attr categories: List of the categories present in the inventory.
    :attr gdf: The GeoPandas DataFrame that represent the whole inventory.
        The geometry column contains all the grid cells.
        Optional columns:

            * For Vertical profiles, use either absolute or range:

                * _heigth: (float) The height of the emission source.
                * _heigth_min: (float) The min height of the emission source.
                * _heigth_max: (float) The min height of the emission source.

        The other columns should contain the emission value for the substances
        and the categories.
    :attr gdfs: Some inventories are given on more than one grid.
        For example, :py:class:`MapLuftZurich` is given on a grid
        where every category has different shape file.
        In this case gdf must be set to None and gdfs will be
        a dictionnary mapping only the categories desired.
    :attr history: Stores all the operations that happened to this inventory.

    .. note::
        If your data contains point sources, the data on them must be stored in
        the gdfs, as :attr:`gdf` is only valid for the inventory grid.
        A gdf should contain only point sources.

    """

    name: str
    grid: Grid
    substances: list[Substance]
    categories: list[str]
    gdf: gpd.GeoDataFrame | None
    gdfs: dict[str, gpd.GeoDataFrame] | None
    geometry: gpd.GeoSeries

    history: list[str]

    def __init__(self) -> None:
        self.history = [f"Created as {type(self).__name__}"]

    @property
    def geometry(self) -> gpd.GeoSeries:
        return self.gdf.geometry

    @property
    def categories(self) -> list[str]:
        return list(
            set(
                [
                    cat
                    for cat, _ in self.gdf.columns
                    if not isinstance(self.gdf[(cat, _)].dtype, gpd.array.GeometryDtype)
                ]
            )
            | set(self.gdfs.keys())
        )

    def copy(self, no_gdfs: bool = False) -> Inventory:
        """Copy the inventory."""
        inv = Inventory()
        inv.__class__ = self.__class__
        inv.history = self.history.copy()
        if hasattr(self, "grid"):
            inv.grid = self.grid

        if not no_gdfs:
            if self.gdf is not None:
                inv.gdf = self.gdf.copy(deep=True)
            else:
                inv.gdf = None
            if self.gdfs is not None:
                inv.gdfs = {key: gdf.copy(deep=True) for key, gdf in self.gdfs.items()}
            else:
                inv.gdfs = None

        inv.history.append(f"Copied from {type(self).__name__} to {inv}.")
        return inv

    def get_emissions(
        self, category: str, substance: str, ignore_point_sources: bool = False
    ):
        """Get the emissions of the requested category and substance.

        In case you have point sources the will be assigned their correct grid cells.

        :arg ignore_point_sources: Whether points sources should not be counted.
        .. note::
            Internally emiproc stores categories and substances as a tuple
            in the header of the gdf: (category, substance),
            or uses the gdfs dictonary for {category: df} where the
            df has substances in the header.
            If you combined the two, a category not in the df should
            be present in the gdfs.
            If you have an optimized way of doing this, you can reimplement
            this function in your :py:class:`Inventory` .
        """
        tuple_name = (category, substance)
        if tuple_name in self.gdf:
            return self.gdf[tuple_name]
        if category in self.gdfs.keys():
            gdf = self.gdfs[category]
            # check if it is point sources
            if len(gdf) == 0 or isinstance(gdf.geometry.iloc[0], Point):
                if ignore_point_sources:
                    return np.zeros(len(gdf))
                else:
                    return weights_remap(
                        get_weights_mapping(
                            Path(".emiproc")
                            / f"Point_source_{type(self).__name__}_{category}",
                            gdf.geometry,
                            self.gdf.geometry,
                            loop_over_inv_objects=True,
                        ),
                        gdf[substance],
                        len(self.gdf),
                    )
            else:
                return gdf[substance]
        raise IndexError(f"Nothing found for {category}, {substance}")

    @classmethod
    def from_gdf(
        cls,
        gdf: gpd.GeoDataFrame,
        name: str = "custom_from_gdf",
        gdfs: dict[str, gpd.GeoDataFrame] = {},
    ) -> Inventory:
        """The gdf must be a two level gdf with (category, substance)."""
        inv = Inventory()
        inv.name = name
        inv.gdf = gdf
        inv.gdfs = gdfs

        return inv



class EmiprocNetCDF(Inventory):
    """An output from emiproc.

    Useful if you need to process again an inventory.
    """

    def __init__(self, file: PathLike) -> None:
        super().__init__()


if __name__ == "__main__":
    test_inv = Inventory()
