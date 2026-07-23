import numpy as np
import pandas as pd
from datetime import datetime, timedelta
#from utils import getTmean, tmean
from emergence import getEmergence_vector, getEmergence



# Wintering Mortality Model

def getWinteringTemperature(self, col, row, year, dev_threshold=6.53):
        
    
        startdate = datetime(year, 11, 1)
        #enddate = datetime(year+1, 2, 1)
        try:
            enddate = getEmergence(col, row, year+1)
            enddate = datetime(enddate.year, enddate.month, enddate.day)
        except:
            enddate = datetime(year+1, 2, 1)

        print(enddate)

        temps = []
    
        while startdate < enddate:
            daily_tmean = self.getTmean(col, row, startdate.day, startdate.month, startdate.year)
            temps.append(daily_tmean)
    
            startdate += timedelta(days=1)
        
        winter_temp = np.mean(temps)

        if winter_temp > dev_threshold:
            return {
                "winter_temp": winter_temp,
                "mortality": 0.5,
                "temps" : temps
            }
        else:
            return {
                "winter_temp": winter_temp,
                "mortality": 0,
                "temps" : temps
            }



# prepare winter temperature data
winterTmean_dict = {}
def prepareWinterTmean(year, tmean):
    if year in winterTmean_dict:
        return winterTmean_dict[year]

    # copy and rename columns
    tmean_copy = tmean.copy()
    cols_c =  tmean_copy.columns.tolist()[5:]
    cols_c_n = [f"year_{col}" for col in cols_c]
    cols_c_n_d = dict(zip(cols_c, cols_c_n))
    tmean_copy.rename(columns=cols_c_n_d, inplace=True)

    # filter for November, December and January to June of the next year
    tmean_11 = tmean_copy.filter(like=f"year_{year}11")
    tmean_11['grid_id'] = tmean['grid_id']
    tmean_12 = tmean_copy.filter(like=f"year_{year}12")
    tmean_12['grid_id'] = tmean['grid_id']
    tmean_01 = tmean_copy.filter(like=f"year_{year+1}01")
    tmean_01['grid_id'] = tmean['grid_id']
    tmean_02 = tmean_copy.filter(like=f"year_{year+1}02")
    tmean_02['grid_id'] = tmean['grid_id']
    tmean_03 = tmean_copy.filter(like=f"year_{year+1}03")
    tmean_03['grid_id'] = tmean['grid_id']
    tmean_04 = tmean_copy.filter(like=f"year_{year+1}04")
    tmean_04['grid_id'] = tmean['grid_id']
    tmean_05 = tmean_copy.filter(like=f"year_{year+1}05")
    tmean_05['grid_id'] = tmean['grid_id']
    tmean_06 = tmean_copy.filter(like=f"year_{year+1}06")
    tmean_06['grid_id'] = tmean['grid_id']

    # merge the two dataframes
    tmean_merge = pd.merge(tmean_11, tmean_12, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_01, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_02, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_03, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_04, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_05, on='grid_id')
    tmean_merge = pd.merge(tmean_merge, tmean_06, on='grid_id')


    # add col, row and grid_id columns
    tmean_merge['col'] = tmean['col']
    tmean_merge['row'] = tmean['row']
    #tmean_merge['grid_id'] = tmean['grid_id']

    # make sure columns are in the right order
    tmean_merge = tmean_merge[sorted(tmean_merge.columns.tolist())]

    winterTmean_dict[year] = tmean_merge
    
    return tmean_merge


def getWinteringTemperature_vector(self, col,row, year, dev_threshold=6.53):
    #dev_threshold = 6.53
    tmean_merge = prepareWinterTmean(year, self.tmean)
    arr_1 =  tmean_merge[(tmean_merge['col'] == col) & (tmean_merge['row'] == row)].filter(like="year").to_numpy().flatten()
    #winter_temp = np.mean(arr_1)

    # filter for the days between November 1 and emergence date
    emergence = getEmergence_vector(self, col, row, year+1)
    #print(emergence)
    winter_date = datetime(year, 11, 1)
    temps = arr_1[:((emergence - winter_date).days)].tolist()
    winter_temp = np.mean(temps)
    
    if winter_temp > dev_threshold:
        return {
            "winter_temp": winter_temp,
            "mortality": 0.5,
            "temps": temps
        }
    else:
        return {
            "winter_temp": winter_temp,
            "mortality": 0,
            "temps": temps
        }
