# Emergence Model
import datetime
from datetime import datetime, timedelta
#from utils import getTmean, tmean
import pandas as pd
import numpy as np

emergence_dict = {}

def getEmergence(self, col, row, year, dev_threshold=6.53, thermal_temp=209):
    '''
    Get emergence date for a given grid cell
    col: int, column number
    row: int, row number
    year: int, year

    output:
    datetime.date, emergence date
    '''

    dict_key = str(col) + "_" + str(row) + "_" + str(year)
    if dict_key in emergence_dict:
        return emergence_dict[dict_key]

    # function constants
    # thermal_temp = 209 # adam et al
    # dev_temp = 6.53 # adam et al


    starting_date = f"{year}-01-01" # start degree day model from the first day of the year
    starting_date = datetime.strptime(starting_date, "%Y-%m-%d").date()
    cumulative_degrees = 0.0
    new_date = starting_date

    # determine emergence date
    cumulative_degrees = 0.0
    dev_list = []
    while cumulative_degrees < thermal_temp:
        daily_tmean = self.getTmean(col, row, new_date.day, new_date.month, new_date.year)
        try:
            if daily_tmean >= dev_threshold:
                cumulative_degrees += float(daily_tmean - dev_threshold)
                dev_list.append(float(daily_tmean - dev_threshold))
            else:
                dev_list.append(0.0)
        except:
            print(col, row, new_date, daily_tmean)
            

        new_date += timedelta(days=1)

    emergence_dict[dict_key] = new_date

    return new_date #, dev_list



### create a function to get the tmean data between a dates 

# this is the extraction of tmean to calculate emergence for 2023

prepareTmean_dict = {}
def prepareEmergenceTmean(year, tmean):
    '''
    Prepare tmean for a given year for emergence calculation

    it return the data for tmean from November of the previous year to December of the current year
    '''

    if year in prepareTmean_dict:
        return prepareTmean_dict[year]
    tmean_copy = tmean.copy()
    cols_c =  tmean_copy.columns.tolist()[5:]
    cols_c_n = [f"year_{col}" for col in cols_c]
    cols_c_n_d = dict(zip(cols_c, cols_c_n))
    tmean_copy.rename(columns=cols_c_n_d, inplace=True)

    # tmean_11 = tmean_copy.filter(like=f"year_{year-1}11")
    # tmean_11['grid_id'] = tmean['grid_id']
    # tmean_12 = tmean_copy.filter(like=f"year_{year-1}12")
    # tmean_12['grid_id'] = tmean['grid_id']

    tmean_year = tmean_copy.filter(like=f"year_{year}")
    tmean_year['grid_id'] = tmean['grid_id']

    #tmean_merge = pd.merge(tmean_11, tmean_12, on='grid_id')
    #tmean_merge = pd.merge(tmean_merge, tmean_year, on='grid_id')

    tmean_merge = tmean_year # remove the 11 and 12 months data

    tmean_merge['col'] = tmean['col']
    tmean_merge['row'] = tmean['row']

    # make sure columns are in the right order
    tmean_merge = tmean_merge[sorted(tmean_merge.columns.tolist())]

    prepareTmean_dict[year] = tmean_merge
    
    return tmean_merge


def getEmergence_vector(self, col, row, year, dev_threshold=6.53, cumulative_threshold=209):
    
    # dev_threshold = 6.53
    # cumulative_threshold = 209

    tmean_merge = prepareEmergenceTmean(year, self.tmean)
    arr_1 =  tmean_merge[(tmean_merge['col'] == col) & (tmean_merge['row'] == row)].filter(like="year").to_numpy().flatten()
    arr_2 = arr_1 - dev_threshold
    arr_3 = np.where(arr_2 < 0, 0, arr_2)
    arr_4 = arr_3.cumsum()
    first_element_index = np.argwhere(arr_4 > cumulative_threshold)[0][0]

    emergence = datetime(year,1,1) + timedelta(days= int(first_element_index) + 1)
    #emergence = datetime(year,1,1) + timedelta(days= int(first_element_index) + 1)
    return datetime.fromtimestamp(emergence.timestamp())
    #return emergence#.strftime("%Y-%m-%d")