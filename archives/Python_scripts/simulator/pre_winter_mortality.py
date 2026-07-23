import pandas as pd
from datetime import datetime, timedelta
#from utils import getTmean, tmean
import numpy as np


# Pre-wintering Mortality Model

def getPreWinteringMortality(self, col, row, year, pre_winter_delta=0.0025, dev_threshold=15, startdate = [8,15], enddate=[10,1]):

    # startdate = datetime(year, 8, 15)
    # enddate = datetime(year, 10, 1)

    startdate = datetime(year, startdate[0], startdate[1])
    enddate = datetime(year, enddate[0], enddate[1])

    mortality = 0
    dev_days = 0
    cumulative_degrees = 0
    
    while startdate < enddate:
        daily_tmean = self.getTmean(col, row, startdate.day, startdate.month, startdate.year)
        if daily_tmean > dev_threshold:
            mortality += pre_winter_delta
            dev_days += 1
            cumulative_degrees += float(daily_tmean - dev_threshold)

        startdate += timedelta(days=1)

    return {
        "mortality": mortality,
        "dev_days": dev_days,
        "cumulative_degrees": cumulative_degrees
    }
    

preWinterTmean_dict = {}
def preparePreWinterTmean(year, tmean):
    if year in preWinterTmean_dict:
        return preWinterTmean_dict[year]
    
    # copy and rename columns
    tmean_copy = tmean.copy()
    cols_c =  tmean_copy.columns.tolist()[5:]
    cols_c_n = [f"year_{col}" for col in cols_c]
    cols_c_n_d = dict(zip(cols_c, cols_c_n))
    tmean_copy.rename(columns=cols_c_n_d, inplace=True)

    # filter for august, september and october
    # tmean_08 = tmean_copy.filter(like=f"year_{year}08")
    # tmean_08['grid_id'] = tmean['grid_id']
    # tmean_09 = tmean_copy.filter(like=f"year_{year}09")
    # tmean_09['grid_id'] = tmean['grid_id']
    # tmean_10 = tmean_copy.filter(like=f"year_{year}10")
    # tmean_10['grid_id'] = tmean['grid_id']

    # merge the two dataframes
    # tmean_merge = pd.merge(tmean_08, tmean_09, on='grid_id')
    # tmean_merge = pd.merge(tmean_merge, tmean_10, on='grid_id')

    tmean_year = tmean_copy.filter(like=f"year_{year}")
    tmean_merge = tmean_year

    # add col, row and grid_id columns
    tmean_merge['col'] = tmean['col']
    tmean_merge['row'] = tmean['row']
    tmean_merge['grid_id'] = tmean['grid_id']

    # make sure columns are in the right order
    tmean_merge = tmean_merge[sorted(tmean_merge.columns.tolist())]

    preWinterTmean_dict[year] = tmean_merge
    
    return tmean_merge


def getPreWinteringMortality_vector(self, col, row, year, pre_winter_delta=0.0025, dev_threshold=15, startdate = [8,15], enddate=[10,1]):

    #dev_threshold = 6.53
    #dev_threshold = 15

    year_begin = datetime(year, 1, 1)
    startdate = datetime(year, startdate[0], startdate[1])
    enddate = datetime(year, enddate[0], enddate[1])

    tmean_merge = preparePreWinterTmean(year, self.tmean)
    arr_1 =  tmean_merge[(tmean_merge['col'] == col) & (tmean_merge['row'] == row)].filter(like="year").to_numpy().flatten()
    arr_t1 = arr_1[(startdate - year_begin).days: (enddate - year_begin).days]
    arr_2 = arr_t1 - dev_threshold
    arr_3 = np.where(arr_2 < 0, 0, arr_2)
   
    count = np.count_nonzero(arr_3 > 0)


    return {
        "mortality": count * pre_winter_delta,
        "dev_days": count,
        "cumulative_degrees": np.sum(arr_3)
    }
