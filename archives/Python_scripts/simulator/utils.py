import pandas as pd
import re


ppt = pd.read_csv('/Users/edwardamoah/Documents/GitHub/OsmiaPopModel/output/ppt_prism_new_york_data.csv')
tmean = pd.read_csv('/Users/edwardamoah/Documents/GitHub/OsmiaPopModel/output/tmean_prism_new_york_data.csv')
#forage = pd.read_csv('/Users/edwardamoah/Documents/GitHub/OsmiaPopModel/output/foraging_quality_pennsylvania_data.csv')
forage = pd.read_csv('/Users/edwardamoah/Documents/GitHub/OsmiaPopModel/output/tmean_prism_new_york_data.csv')

cols = tmean.columns.tolist()

# create new columns 
new_cols = []
for col in cols:
    if "Forage" in col:
        code = col.split("_")[1]
        number = re.findall(r'\d+', code)[0]
        new_cols.append(number)
    else:
        new_cols.append(col)

new_cols

# rename columns
tmean = tmean.rename(columns=dict(zip(tmean.columns, new_cols)))

# create grid_id column
tmean["grid_id"] = tmean["col"].astype(str) + "_" + tmean["row"].astype(str)

possible_cols = tmean.col.tolist()
possible_rows = tmean.row.tolist()

forage["grid_id"] = forage["col"].astype(str) + "_" + forage["row"].astype(str)

def getGridForageQuality(col, row, year, forage=forage):
    grid_id = str(col) + "_" + str(row)
    try:
        #return forage.query(f" grid_id == '{grid_id}' and year == {year}")['Forage_spring_1km'].values[0]
        return float(forage.query(f" grid_id == '{grid_id}' ")['sprng__'].values[0])
    except:
        return getGridForageQuality(col, row, year + 1)


def getGridForageQuality_vectorized(cols, rows, years,forage=forage):
    # Ensure grid_id is available in the forage DataFrame
    grid_ids = str(cols) + "_" + str(rows)

    # Match grid_id and year across entire DataFrame without looping
    mask = (forage['grid_id'].isin(grid_ids)) & (forage['year'].isin(years))

    # Extract the corresponding forage quality values
    #forage_quality = forage.loc[mask, 'Forage_spring_1km']
    forage_quality = forage.loc[mask, 'spring__']

    return forage_quality

################# tmean data #################

cols = tmean.columns.tolist()

new_cols = []
for col in cols:
    if "PRISM_tmean" in col:
        new_cols.append(col.split("_")[-2])
    else:
        new_cols.append(col)
new_cols

tmean = tmean.rename(columns=dict(zip(tmean.columns, new_cols)))


tmean["grid_id"] = tmean["col"].astype(str) + "_" + tmean["row"].astype(str)

def getTmean(col, row, day, month, year, tmean=tmean):
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
    if month < 10:
        month = "0" + str(month)
    if day < 10:
        day = "0" + str(day)
    date = str(year) + "" + str(month) + "" + str(day)
    grid_id = str(col) + "_" + str(row)
    tmean = tmean[tmean["grid_id"] == grid_id][date].values[0]
    return float(tmean)

############### ppt data #################

cols = ppt.columns.tolist()

new_cols = []
for col in cols:
    if "PRISM_ppt" in col:
        new_cols.append(col.split("_")[-2])
    else:
        new_cols.append(col)

ppt = ppt.rename(columns=dict(zip(ppt.columns, new_cols)))

ppt["grid_id"] = ppt["col"].astype(str) + "_" + ppt["row"].astype(str)

def getPpt(col, row, day, month, year, ppt=ppt):
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
    if month < 10:
        month = "0" + str(month)
    if day < 10:
        day = "0" + str(day)
    date = str(year) + "" + str(month) + "" + str(day)
    grid_id = str(col) + "_" + str(row)
    ppt = ppt[ppt["grid_id"] == grid_id][date].values[0]
    return float(ppt)