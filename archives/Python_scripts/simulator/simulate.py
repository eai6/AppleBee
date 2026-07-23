import pandas as pd
import re
import emergence
import egg_production 
import egg_and_larva_mortality
import pre_winter_mortality
import winter_mortality
import traceback

class Simulator:
    def __init__(self, ppt_path:str="", tmean_path:str="", forage_path:str="", vectorize:bool=True):

        self.vectorize = vectorize
        self.ppt = pd.read_csv(ppt_path)
        self.tmean = pd.read_csv(tmean_path)
        self.forage = pd.read_csv(forage_path)
        

        cols = self.tmean.columns.tolist()

        # create new columns 
        new_cols = []
        for col in cols:
            if "Forage" in col:
                code = col.split("_")[1]
                number = re.findall(r'\d+', code)[0]
                new_cols.append(number)
            else:
                new_cols.append(col)

        #new_cols

        # rename columns
        self.tmean = self.tmean.rename(columns=dict(zip(self.tmean.columns, new_cols)))

        # create grid_id column
        self.tmean["grid_id"] = self.tmean["col"].astype(str) + "_" + self.tmean["row"].astype(str)

        self.forage["grid_id"] = self.forage["col"].astype(str) + "_" + self.forage["row"].astype(str)

        cols = self.tmean.columns.tolist()

        new_cols = []
        for col in cols:
            if "PRISM_tmean" in col:
                new_cols.append(col.split("_")[-2])
            else:
                new_cols.append(col)
        new_cols

        self.tmean = self.tmean.rename(columns=dict(zip(self.tmean.columns, new_cols)))

        self.tmean["grid_id"] = self.tmean["col"].astype(str) + "_" + self.tmean["row"].astype(str)

        cols = self.ppt.columns.tolist()

        new_cols = []
        for col in cols:
            if "PRISM_ppt" in col:
                new_cols.append(col.split("_")[-2])
            else:
                new_cols.append(col)

        self.ppt = self.ppt.rename(columns=dict(zip(self.ppt.columns, new_cols)))

        self.ppt["grid_id"] = self.ppt["col"].astype(str) + "_" + self.ppt["row"].astype(str)



    def getGridForageQuality(self, col, row, year, recursive_depth=0):
        forage = self.forage
        grid_id = str(col) + "_" + str(row)
        try:
            return float(forage.query(f" grid_id == '{grid_id}' ")[f'spring_resource_quality_{year}'].values[0])
        except:
            if recursive_depth == 0:
                return self.getGridForageQuality(col, row, year+1, recursive_depth=1)
            elif recursive_depth == 1:
                return self.getGridForageQuality(col+1, row, year, recursive_depth=2)
            elif recursive_depth == 2:
                return self.getGridForageQuality(col, row-1, year, recursive_depth=3)
            elif recursive_depth == 3:
                return self.getGridForageQuality(col, row+1, year, recursive_depth=4)
            elif recursive_depth == 4:
                return self.getGridForageQuality(col-1, row-1, year, recursive_depth=5)
            elif recursive_depth == 5:
                return self.getGridForageQuality(col+1, row+1, year, recursive_depth=6)
            elif recursive_depth == 6:
                return self.getGridForageQuality(col-1, row+1, year, recursive_depth=7)
            elif recursive_depth == 7:
                return self.getGridForageQuality(col+1, row-1, year, recursive_depth=8)
            elif recursive_depth == 8:
                return self.getGridForageQuality(col-1, row, year, recursive_depth=9)
            elif recursive_depth == 9:
                return self.getGridForageQuality(col, row, year-1, recursive_depth=10)
            elif recursive_depth == 10:
                return 0.5

            


    def getGridForageQuality_vectorized(self, cols, rows, years):
        forage = self.forage
        # Ensure grid_id is available in the forage DataFrame
        grid_ids = str(cols) + "_" + str(rows)

        # Match grid_id and year across entire DataFrame without looping
        mask = (forage['grid_id'].isin(grid_ids)) & (forage['year'].isin(years))

        # Extract the corresponding forage quality values
        #forage_quality = forage.loc[mask, 'Forage_spring_1km']
        forage_quality = forage.loc[mask, 'spring__']

        return forage_quality
    

    def getTmean(self, col, row, day, month, year):
        '''
        Get temperature data for a given grid cell
        col: int, column number
        row: int, row number
        day: int, day of the month
        month: int, month of the year
        year: int, year
        tmean: pd.DataFrame, temperature data

        output:
        float, temperature in degrees celcius
        '''
        tmean = self.tmean
        if month < 10:
            month = "0" + str(month)
        if day < 10:
            day = "0" + str(day)
        date = str(year) + "" + str(month) + "" + str(day)
        grid_id = str(col) + "_" + str(row)
        tmean = tmean[tmean["grid_id"] == grid_id][date].values[0]
        return float(tmean)

        ############### ppt data #################


    def getPpt(self, col, row, day, month, year):
        '''
        Get precipitation data for a given grid cell
        col: int, column number
        row: int, row number
        day: int, day of the month
        month: int, month of the year
        year: int, year
        ppt: pd.DataFrame, precipitation data

        output:
        float, precipitation in mm
        '''
        ppt = self.ppt
        if month < 10:
            month = "0" + str(month)
        if day < 10:
            day = "0" + str(day)
        date = str(year) + "" + str(month) + "" + str(day)
        grid_id = str(col) + "_" + str(row)
        ppt = ppt[ppt["grid_id"] == grid_id][date].values[0]
        return float(ppt)


    def emergence(self, col, row, year, dev_threshold=6.53, thermal_temp=209, vectorize=None):
        if vectorize is None:
            vectorize = self.vectorize
        
        if vectorize:
            return emergence.getEmergence_vector(self, col, row, year, dev_threshold, thermal_temp)
        return emergence.getEmergence(self, col, row, year, dev_threshold, thermal_temp)
    
    def eggProduction(self, col, row, emergence, longevity=22, temperature_threshold=13.9, mating_days=2, precipitation_threshold=5, forage_threshold=0.5, vectorize=None):
        if vectorize is None:
            vectorize = self.vectorize
        
        if vectorize:
            return egg_production.getSpatiallyExplicitReproduction_vector(self, col, row, emergence, longevity, temperature_threshold, mating_days, precipitation_threshold, forage_threshold)
        return egg_production.getSpatiallyExplicitReproduction(self, col, row, emergence, longevity, temperature_threshold, mating_days, precipitation_threshold, forage_threshold)
    
    def eggLarvaMortality(self, col, row, emergence, reproduction, mating_days=2, egg_larva_days=18, longevity=22, mortality_delta=0.1, lower_thermal_threshold=10, upper_thermal_threshold=30, vectorize=None):
        if vectorize is None:
            vectorize = self.vectorize

        if vectorize:
            return egg_and_larva_mortality.getEggLarvaMortality_vector(self, col, row, emergence, reproduction, mating_days, egg_larva_days, longevity, mortality_delta, lower_thermal_threshold, upper_thermal_threshold)
        return egg_and_larva_mortality.getEggLarvaMortality(self, col, row, emergence, reproduction, mating_days, egg_larva_days, longevity, mortality_delta, lower_thermal_threshold, upper_thermal_threshold)
    
    def preWinterMortality(self, col, row, year, pre_winter_delta=0.0025, dev_temp=15, startdate=[8,15], enddate=[10,1], vectorize=None):
        if vectorize is None:
            vectorize = self.vectorize

        if vectorize:
            return pre_winter_mortality.getPreWinteringMortality_vector(self, col, row, year, pre_winter_delta, dev_temp, startdate, enddate)
        return pre_winter_mortality.getPreWinteringMortality(self, col, row, year, pre_winter_delta, dev_temp, startdate, enddate)
    
    def winterMortality(self, col, row, year, winter_delta=0.0025, dev_temp=15, vectorize=None):
        if vectorize is None:
            vectorize = self.vectorize

        if vectorize:
            return winter_mortality.getWinteringTemperature_vector(self, col, row, year, winter_delta, dev_temp)
        return winter_mortality.getWinteringTemperature(self, col, row, year, winter_delta, dev_temp)