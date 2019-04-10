from make_online_emissions import *
from glob import glob
import numpy as np

def get_ch_emi(filename):
    """read in meteotest swiss inventory data
     
       output: emi_trans[lon][lat] (emission data per species per category)
    """
    no_data= -9999
    emi = np.loadtxt(filename, skiprows=6)
    
    emi_new = np.empty((np.shape(emi)[0],np.shape(emi)[1]))   # create the same dimention as emi
    for i in range(np.shape(emi)[0]):
        for j in range(np.shape(emi)[1]):            
            emi_new[i,j]=emi[np.shape(emi)[0]-1-i,j] 
            if emi_new[i,j]==no_data:
               emi_new[i,j]=0 
    
    emi_trans = np.transpose(emi_new)
    
 
    return emi_trans

def main(cfg_path):
    """ The main script for processing TNO inventory. 
    Takes a configuration file as input"""

    """Load the configuration file"""
    cfg = load_cfg(cfg_path)

    """Load or compute the country mask"""
    country_mask = get_country_mask(cfg)
    country_mask = np.transpose(country_mask)
    mask = country_mask != country_codes['CH']
    print('Only use data inside "CH" according to country_mask '
          '(country code %d)' % country_codes['CH'])

    """Set names for longitude and latitude"""
    lonname = "rlon"; latname="rlat"
    if cfg.pollon==180 and cfg.pollat==90:
        lonname = "lon"; latname="lat"

    """Load or compute the interpolation map"""
    interpolation = get_interpolation(cfg, None, inv_name=cfg.origin,
                                      filename='mapping_' + cfg.origin + '.npy')


    """Starts writing out the output file"""
    output_path = os.path.join(cfg.output_path, 
                               "emis_" + str(cfg.year) + "_" + cfg.gridname + ".nc")
    with nc.Dataset(output_path,"w") as out:
        prepare_output_file(cfg,out,country_mask)
        """
        Swiss inventory specific (works with MeteoTest, MaiolicaCH4,
        and CarboCountCO2)   
        """
        total_flux = {}
        for var in cfg.species:
            total_flux[var] = np.zeros((cfg.ny,cfg.nx))

        for cat in cfg.ch_cat:            
            for var in cfg.species:                  
                if cfg.origin == 'meteotest':
                    constfile = os.path.join(cfg.input_path,
                                             ''.join(['e',cat.lower(),'15_',
                                                      var.lower(),'*'])
                                            )
                    out_var_name = var + "_" + cat
                elif cfg.origin == 'carbocount':
                    constfile = os.path.join(cfg.input_path, 'tot_co2_kg.txt')
                    out_var_name = var
                elif cfg.origin == 'maiolica':
                    constfile = os.path.join(cfg.input_path, 'ch4_tot.txt')
                    out_var_name = var
                else:
                    print("Wrong origin in the config file.")
                    raise ValueError

                emi= np.zeros((cfg.ch_xn,cfg.ch_yn))
                for filename in sorted(glob(constfile)):                          
                    print(filename)
                    emi += get_ch_emi(filename) #(lon,lat)                                       
                start = time.time()
                out_var = np.zeros((cfg.ny,cfg.nx))           
                for lon in range(np.shape(emi)[0]):
                    for lat in range(np.shape(emi)[1]):
                        for (x,y,r) in interpolation[lon,lat]:
                            out_var[y,x] += emi[lon,lat]*r
                end = time.time()
                print("it takes ",end-start,"sec")    

                """calculate the areas (m^^2) of the COSMO grid"""
                cosmo_area = 1./gridbox_area(cfg)

                """convert unit from kg.year-1.cell-1 to kg.m-2.s-1"""
                out_var *= cosmo_area.T*convfac
                out_var[mask] = 0

                out.createVariable(out_var_name,float,(latname,lonname))
                if lonname == "rlon" and latname == "rlat":
                    out[out_var_name].grid_mapping = "rotated_pole"
                out[out_var_name].units = "kg m-2 s-1"
                out[out_var_name][:] = out_var
                total_flux[var] += out_var


        if cfg.origin == 'meteotest':
            """Calcluate total emission/flux per species"""
            for s in cfg.species:
                out.createVariable(s,float,(latname,lonname))
                out[s].units = "kg m-2 s-1"
                if lonname == "rlon" and latname == "rlat":
                    out[s].grid_mapping = "rotated_pole"
                out[s][:] = total_flux[s]
    


if __name__ == "__main__":
    cfg_name = sys.argv[1]
    main("./config_" + cfg_name)
