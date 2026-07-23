import numpy as np
import pandas as pd
from datetime import datetime, timedelta
#from utils import getTmean, tmean


# Egg and Larva Mortality Model

def getEggLarvaMortality(self, col, row, emergence, reproduction, mating_days=2, egg_larva_days=18, longevity=22, mortality_delta=0.1, lower_thermal_threshold=10, upper_thermal_threshold=30):

    def getEggMortalityProbability(date, tmeans, mortality_delta, egg_larva_days, ldt, udt):

        prob = 0
        cold_days = 0
        hot_days = 0
        for i in range(egg_larva_days): # 4 egg + 14 larva
            if tmeans[date] < ldt or tmeans[date] > udt:
                prob += mortality_delta
                if tmeans[date] < ldt:
                    cold_days += 1
                if tmeans[date] > udt:
                    hot_days += 1
            date = datetime.strptime(date, "%Y-%m-%d").date()
            date += timedelta(days=1)
            date = date.strftime("%Y-%m-%d")

            

        return {
            "prob": prob,
            "cold_days": cold_days,
            "hot_days": hot_days
        }

    total_dev_days = longevity + egg_larva_days - mating_days # days 20 forages + 4 egg + 14 larva

    startdate = emergence + timedelta(days=mating_days)

    tmeans = {}
    for i in range(total_dev_days): # get all the tmeans
        tmeans[startdate.strftime("%Y-%m-%d")] = self.getTmean(col, row, startdate.day, startdate.month, startdate.year)
        startdate += timedelta(days=1)

    egg_mortalities = []
    cold_days = []
    hot_days = []
    for egg_day in reproduction['egg_days']:
        mortality = getEggMortalityProbability(egg_day, tmeans, mortality_delta, egg_larva_days, lower_thermal_threshold, upper_thermal_threshold)
        egg_mortalities.append(mortality['prob'])
        cold_days.append(mortality['cold_days'])
        hot_days.append(mortality['hot_days'])

    egg_mortalities = np.mean(egg_mortalities)
    if egg_mortalities > 1:
        egg_mortalities = 1


    if len(hot_days) == 0:
        return {
            "mortality": 0,
            "cold_days": 0,
            "hot_days": 0
        }

    return {    
        "mortality": egg_mortalities,
        "cold_days": np.mean(cold_days),
        "hot_days": np.mean(hot_days)
    }



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


def getEggLarvaMortality_vector(self, col, row, emergence, reproduction, mating_days=2, egg_larva_days=18, longevity=22, mortality_delta=0.1, lower_thermal_threshold=10, upper_thermal_threshold=30):

    tmean_merge = prepareReproductionTmean(emergence.year, self.tmean)
    arr_t =  tmean_merge[(tmean_merge['col'] == col) & (tmean_merge['row'] == row)].filter(like="year").to_numpy().flatten()
    data_start = datetime(emergence.year, 4, 1)

    cold_days = []
    hot_days = []
    mortality = []
    for date in reproduction['egg_days']:
        date = datetime.strptime(date, "%Y-%m-%d")
        arr_t1 = arr_t[(date - data_start).days: (date - data_start).days + egg_larva_days]
        arr_t2_h = np.where((arr_t1 <= upper_thermal_threshold), 0, 1)
        arr_t2_c = np.where((arr_t1 >= lower_thermal_threshold) , 0, 1)
        cold_days.append(arr_t2_c.sum())
        hot_days.append(arr_t2_h.sum())
        mortality.append((arr_t2_c.sum() + arr_t2_h.sum()) * mortality_delta)

    mortality = np.mean(mortality)
    if mortality > 1:
        mortality = 1
    
    if len(hot_days) == 0:
        return {
            "mortality": 0,
            "cold_days": 0,
            "hot_days": 0
        }


    return {
        "cold_days": np.mean(cold_days),
        "hot_days": np.mean(hot_days),
        "mortality": mortality
    }
