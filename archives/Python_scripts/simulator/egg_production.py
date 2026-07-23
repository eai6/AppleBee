from datetime import datetime, timedelta
import pandas as pd
import numpy as np
#from utils import getTmean, tmean, getGridForageQuality, getPpt, ppt



# Reproduction Model

reproductive_dict = {}

def getSpatiallyExplicitReproduction(self, col, row, emergence, longevity=22, temperature_threshold=13.9, mating_days=2, precipitation_threshold=5, forage_threshold=0.5):
    '''
    Get reproduction date for a given grid cell
    col: int, column number
    row: int, row number
    year: int, year
    emergence: datetime.date, emergence date

    output:
    datetime.date, reproduction date
    '''

    #print(col, row, emergence)

    # dict_key = str(col) + "_" + str(row) + "_" + emergence.strftime("%Y-%m-%d")
    # if dict_key in reproductive_dict:
    #     return reproductive_dict[dict_key]

    # function constants
    eggs = 0
    egg_delta = 1 # change in eggs per day
     # update starting date
    starting_date = emergence + timedelta(days=mating_days)

    # update egg_delta based on foraging quality
    forage_quality = self.getGridForageQuality(col, row, starting_date.year)

    if forage_quality < forage_threshold:
        egg_delta = 1
    else:
        egg_delta = 2

    non_foraging_days = 0
    precipitation_effect = 0
    temperature_effect = 0
    temps = []
    ppts = []
    egg_days = []
    
    for i in range(longevity-mating_days):
        # get daily temperature and precipitation
        daily_tmean = self.getTmean(col, row, starting_date.day, starting_date.month, starting_date.year)
        daily_ppt = self.getPpt(col, row, starting_date.day, starting_date.month, starting_date.year)

        temps.append(daily_tmean)
        ppts.append(daily_ppt)

        #print(daily_tmean, daily_ppt)

        # update eggs
        if daily_tmean >= temperature_threshold and daily_ppt < precipitation_threshold:
            eggs += egg_delta
            egg_days.append(starting_date.strftime("%Y-%m-%d"))
            
        else:
            non_foraging_days += 1
            if daily_tmean < temperature_threshold:
                temperature_effect += 1
            if daily_ppt >= precipitation_threshold:
                precipitation_effect += 1

        # update date
        starting_date += timedelta(days=1)
        

    return_dict = {
        "eggs": eggs,
        "non_foraging_days": non_foraging_days,
        "precipitation_effect": precipitation_effect,
        "temperature_effect": temperature_effect,
        "temps": temps,
        "ppts": ppts,
        "egg_days": egg_days,
        'forage_quality': forage_quality
    }

    # reproductive_dict[dict_key] = return_dict

    return return_dict



# prepare winter temperature data
reproductionTmean_dict = {}
def prepareReproductionTmean(year, tmean):
    if year in reproductionTmean_dict:
        return reproductionTmean_dict[year]
    
    # copy and rename columns
    tmean_copy = tmean.copy()
    cols_c =  tmean_copy.columns.tolist()[5:]
    cols_c_n = [f"year_{col}" for col in cols_c]
    cols_c_n_d = dict(zip(cols_c, cols_c_n))
    tmean_copy.rename(columns=cols_c_n_d, inplace=True)

    # filter for April, May and June
    tmean_04 = tmean_copy.filter(like=f"year_{year}04")
    tmean_04['grid_id'] = tmean['grid_id']
    tmean_05 = tmean_copy.filter(like=f"year_{year}05")
    tmean_05['grid_id'] = tmean['grid_id']
    tmean_06 = tmean_copy.filter(like=f"year_{year}06")
    tmean_06['grid_id'] = tmean['grid_id']
    tmean_07 = tmean_copy.filter(like=f"year_{year}07")
    tmean_07['grid_id'] = tmean['grid_id']

    

    # merge the two dataframes
    tmean_merge = pd.merge(tmean_04, tmean_05, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_06, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_07, on='grid_id')

    # add col, row and grid_id columns
    tmean_merge['col'] = tmean['col']
    tmean_merge['row'] = tmean['row']
    #tmean_merge['grid_id'] = tmean['grid_id']

    # make sure columns are in the right order
    tmean_merge = tmean_merge[sorted(tmean_merge.columns.tolist())]

    reproductionTmean_dict[year] = tmean_merge
    
    return tmean_merge


# prepare winter temperature data
reproductionPpt_dict = {}
def prepareReproductionPpt(year, ppt):
    if year in reproductionPpt_dict:
        return reproductionPpt_dict[year]
    
    # copy and rename columns
    ppt_copy = ppt.copy()
    cols_c =  ppt_copy.columns.tolist()[5:]
    cols_c_n = [f"year_{col}" for col in cols_c]
    cols_c_n_d = dict(zip(cols_c, cols_c_n))
    ppt_copy.rename(columns=cols_c_n_d, inplace=True)

    # filter for April, May and June
    ppt_04 = ppt_copy.filter(like=f"year_{year}04")
    ppt_04['grid_id'] = ppt['grid_id']
    ppt_05 = ppt_copy.filter(like=f"year_{year}05")
    ppt_05['grid_id'] = ppt['grid_id']
    ppt_06 = ppt_copy.filter(like=f"year_{year}06")
    ppt_06['grid_id'] = ppt['grid_id']
    

    # merge the two dataframes
    ppt_merge = pd.merge(ppt_04, ppt_05, on='grid_id')
    ppt_merge = pd.merge(ppt_merge, ppt_06, on='grid_id')

    # add col, row and grid_id columns
    ppt_merge['col'] = ppt['col']
    ppt_merge['row'] = ppt['row']
    #tmean_merge['grid_id'] = tmean['grid_id']

    # make sure columns are in the right order
    ppt_merge = ppt_merge[sorted(ppt_merge.columns.tolist())]

    reproductionPpt_dict[year] = ppt_merge
    
    return ppt_merge



# define vectorize reproduction function

def getSpatiallyExplicitReproduction_vector(self, col, row, emergence, longevity=22, temperature_threshold=13.9, mating_days=2, precipitation_threshold=5, forage_threshold=0.5):

    starting_date = emergence + timedelta(days=mating_days)

    data_start = datetime(emergence.year, 4, 1)

    forage_quality = self.getGridForageQuality(col, row, emergence.year)
    if forage_quality < forage_threshold:
        egg_delta = 1
    else:
        egg_delta = 2

    # prepare temperature data
    tmean_merge = prepareReproductionTmean(emergence.year, self.tmean)

    arr_t =  tmean_merge[(tmean_merge['col'] == col) & (tmean_merge['row'] == row)].filter(like="year").to_numpy().flatten()
    arr_t1 = arr_t[(emergence - data_start).days + mating_days: (emergence - data_start).days + (longevity)]
    arr_t2 = np.where(arr_t1 >= temperature_threshold, 1, 0)

    # prepare precipitation data
    ppt_merge = prepareReproductionPpt(emergence.year, self.ppt)
    arr_p =  ppt_merge[(ppt_merge['col'] == col) & (ppt_merge['row'] == row)].filter(like="year").to_numpy().flatten()
    arr_p1 = arr_p[(emergence - data_start).days + mating_days: (emergence - data_start).days + (longevity)]
    arr_p2 = np.where(arr_p1 < precipitation_threshold, 1, 0)


    arr_c = arr_t2 & arr_p2

    arr_c.sum()

    eggs = arr_c.sum() * egg_delta
    non_foraging_days = (longevity - mating_days) - arr_c.sum()
    precipitation_effect = (longevity - mating_days) - arr_p2.sum()
    temperature_effect = (longevity - mating_days) - arr_t2.sum()
    temps = arr_t1.tolist()
    ppts = arr_p1.tolist()

    egg_days = []
    for i in range(len(arr_c)):
        if arr_c[i] == 1:
            egg_days.append((starting_date + timedelta(days=i)).strftime("%Y-%m-%d")) 

    return {
        "eggs": eggs,
        "non_foraging_days": non_foraging_days,
        "precipitation_effect": precipitation_effect,
        "temperature_effect": temperature_effect,
        "temps": temps,
        "ppts": ppts,
        "egg_days": egg_days,
        'forage_quality': forage_quality
    }
