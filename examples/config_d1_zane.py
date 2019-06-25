tnoCamsPath = "/input/TNOMACC/MACCIII/TNO_MACC_III_emissions_2011.nc"
tno_xmin = -30.0
tno_xmax = 60.0
tno_ymin = 30.0
tno_ymax = 72.0
tno_dx = 1 / 8.0
tno_dy = 1 / 16.0

species = [
    "CO",
    "NOX",
    "NMVOC",
    "SO2",
    "NH3",
    "PM10",
    "PM25",
]  # , 'PM10', 'CH4', 'SO2', 'NMVOC', 'NH3', 'NOx'] #among 'CO2', 'PM2.5', 'CO', 'PM10', 'CH4', 'SO2', 'NMVOC', 'NH3', 'NOx'

cat_kind = "SNAP"
# output cat
snap = [1, 2, 34, 5, 6, 71, 72, 73, 74, 75, 8, 9, 10]
# input cat
tno_snap = [1, 2, 34, 5, 6, 71, 72, 73, 74, 75, 8, 9, 10]
year = 2011
gridname = "d1_zane"
output_path = "./testdata/d1_offline/zane/"
# output_path ="./testdata/d1_online/tno/"

offline = True
# offline=False

# Domain
# Europe domain, rotated pole coordinate
dx = 0.0625
dy = 0.0625
pollon = -171.0
pollat = 42.5

if not offline:
    xmin = -24.96875  # -2*dx
    ymin = -21.84375  # -2*dy
    nx = 800  # +4
    ny = 700  # +4
else:
    xmin = -24.96875 - 2 * dx
    ymin = -21.84375 - 2 * dy
    nx = 800 + 4
    ny = 700 + 4