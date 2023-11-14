import pytest

import numpy as np
import xarray as xr
from emiproc.profiles.operators import concatenate_profiles, weighted_combination
from emiproc.profiles.temporal_profiles import (
    AnyProfiles,
    TemporalProfile,
    DailyProfile,
    WeeklyProfile,
    MounthsProfile,
    CompositeTemporalProfiles,
    SpecificDayProfile,
    HourOfYearProfile,
    HourOfLeapYearProfile,
    make_composite_profiles,
)
from emiproc.profiles.utils import merge_indexes
from emiproc.tests_utils.temporal_profiles import (
    daily_test_profile,
    weekly_test_profile,
    mounths_test_profile,
)


@pytest.mark.parametrize(
    "profile_type",
    [
        TemporalProfile,
        DailyProfile,
        WeeklyProfile,
        MounthsProfile,
        HourOfYearProfile,
        HourOfLeapYearProfile,
    ],
)
def test_create_profiles(profile_type):
    profile = profile_type()
    pytest.approx(profile.ratios.sum(axis=1), 1)
    assert profile.ratios.shape == (1, profile.size)


def test_multiple_profiles():
    p = TemporalProfile(
        [
            [0.1, 0.2, 0.3, 0.4],
            [0.1, 0.2, 0.3, 0.4],
            [0.1, 0.2, 0.3, 0.4],
        ],
        size=4,
    )
    assert p.ratios.shape == (3, 4)
    assert p.n_profiles == 3
    assert p.size == 4
    assert len(p) == 3


def test_composite_temporal_profiles():
    p = CompositeTemporalProfiles(
        [
            [TemporalProfile(), DailyProfile()],
            [WeeklyProfile()],
        ]
    )
    assert p.n_profiles == 2
    assert len(p[0]) == 2
    assert len(p[1]) == 1


def test_composite_error_wrong_type():
    with pytest.raises(TypeError):
        CompositeTemporalProfiles(
            [
                [TemporalProfile(), DailyProfile()],
                [WeeklyProfile()],
                [1],
            ]
        )


def test_iterate_over_composite():
    profiles = CompositeTemporalProfiles(
        [
            [TemporalProfile(), DailyProfile()],
            [WeeklyProfile()],
        ]
    )
    for profile in profiles:
        assert isinstance(profile, list)
        for p in profile:
            assert isinstance(p, TemporalProfile)


def test_composite_ratios():
    profiles = CompositeTemporalProfiles(
        [
            [WeeklyProfile(), DailyProfile()],
            [WeeklyProfile()],
        ]
    )
    assert profiles.ratios.shape == (2, 7 + 24)

    # test we can create back from the ratios
    new_profiles = CompositeTemporalProfiles.from_ratios(
        profiles.ratios, profiles.types
    )

    for old, new in zip(profiles, new_profiles):
        assert isinstance(old, list)
        assert isinstance(new, list)
        assert old == new
        for o, n in zip(old, new):
            assert isinstance(o, TemporalProfile)
            assert isinstance(n, TemporalProfile)
            assert o == n


def test_internals():
    # This test should not need to exist and could be invalid if someone changes the internal mechanics

    p = CompositeTemporalProfiles(
        [
            [WeeklyProfile(), DailyProfile()],
            [WeeklyProfile()],
        ]
    )
    assert WeeklyProfile in p._profiles
    assert DailyProfile in p._profiles
    assert WeeklyProfile in p._indexes
    assert DailyProfile in p._indexes
    np.testing.assert_array_equal(p._indexes[WeeklyProfile], [0, 1])
    np.testing.assert_array_equal(p._indexes[DailyProfile], [0, -1])
    assert len(p._profiles[WeeklyProfile]) == 2
    assert len(p._profiles[DailyProfile]) == 1


def test_join_composites():
    joined = CompositeTemporalProfiles.join(
        CompositeTemporalProfiles(
            [
                [WeeklyProfile(), DailyProfile()],
                [WeeklyProfile()],
            ]
        ),
        CompositeTemporalProfiles(
            [
                [WeeklyProfile(), DailyProfile()],
                [WeeklyProfile()],
            ]
        ),
        CompositeTemporalProfiles(
            [
                [WeeklyProfile()],
            ]
        ),
    )
    assert joined.n_profiles == 5
    assert len(joined[0]) == 2
    assert len(joined[1]) == 1
    assert len(joined[2]) == 2
    assert len(joined[3]) == 1
    assert len(joined[4]) == 1


def test_equality():
    p1 = WeeklyProfile()
    p2 = WeeklyProfile()
    p3 = WeeklyProfile([0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.0])
    p4 = WeeklyProfile([0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.0])
    assert p1 == p2
    assert p1 != p3
    assert p3 == p4


def test_concatenate_composite():
    cat_profiles = concatenate_profiles(
        [
            CompositeTemporalProfiles(
                [
                    [WeeklyProfile(), DailyProfile()],
                    [WeeklyProfile()],
                ]
            ),
            CompositeTemporalProfiles(
                [
                    [WeeklyProfile(), DailyProfile()],
                    [WeeklyProfile()],
                ]
            ),
        ]
    )
    assert cat_profiles.n_profiles == 4
    assert len(cat_profiles[0]) == 2
    assert len(cat_profiles[1]) == 1
    assert len(cat_profiles[2]) == 2
    assert len(cat_profiles[3]) == 1


def test_concatenate_lists():
    cat_profiles = concatenate_profiles(
        [
            [
                [WeeklyProfile(), DailyProfile()],
                [WeeklyProfile()],
            ],
            [
                [WeeklyProfile(), DailyProfile()],
                [WeeklyProfile()],
            ],
        ]
    )
    assert cat_profiles.n_profiles == 4
    assert len(cat_profiles[0]) == 2
    assert len(cat_profiles[1]) == 1
    assert len(cat_profiles[2]) == 2
    assert len(cat_profiles[3]) == 1


def test_wrong_list_concatenate():
    pytest.raises(
        TypeError,
        concatenate_profiles,
        [
            [WeeklyProfile(), DailyProfile()],
            [WeeklyProfile()],
        ],
    )


def test_merging_profiles():
    profiles = AnyProfiles(
        [
            MounthsProfile(
                [
                    [0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.1, 0.2, 0.4, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                ],
            ),
            WeeklyProfile([0.1, 0.2, 0.3, 0.1, 0.0, 0.0, 0.3]),
        ]
    )
    assert profiles.n_profiles == 3
    dss = [
        xr.DataArray(
            np.array([[0, 1, 0], [1, -1, 0]]),
            coords={
                "category": ["blek", "liku"],
                "substance": ["CO2", "CH4", "N2O"],
            },
        ).expand_dims(
            {
                "profile": ["MounthsProfile"],
            }
        ),
        xr.DataArray(
            np.array([[2, -1], [2, 2]]),
            coords={
                "category": ["blek", "liku"],
                "substance": ["CO2", "CH4"],
            },
        ).expand_dims(
            {
                "profile": ["WeeklyProfile"],
            }
        ),
    ]

    combined_indexes = merge_indexes(dss)

    make_composite_profiles(profiles, combined_indexes)


def test_weighted_combination():
    weights = np.array([1, 2, 3])
    new_profile = weighted_combination(
        [
            WeeklyProfile([0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.0]),
            WeeklyProfile([0.2, 0.1, 0.3, 0.4, 0.0, 0.0, 0.0]),
            WeeklyProfile([0.3, 0.0, 0.3, 0.4, 0.0, 0.0, 0.0]),
        ],
        weights=weights,
    )

    # The combination should give the same as summing the emissions one by one
    assert np.allclose(
        new_profile.ratios.reshape(-1),
        np.array([7 / 30, 2 / 30, 0.3, 0.4, 0.0, 0.0, 0.0]),
    )


if __name__ == "__main__":
    pytest.main([__file__])
