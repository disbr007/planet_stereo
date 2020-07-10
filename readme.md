# planet_stereo

This repo utilizes the Planet API to facilitate ordering imagery. The primary uses are:
1. Creating a "search request" based on a query
2. Getting a footprint from a search request
3. Ordering and downloading imagery.

## Installation

Using conda:
```
conda env create -f planet_stereo.yml
conda activate planet_stereo
```

## Usage
To create a search from the command line:  
```
python create_saved_search.py --name my_search --item_types PSScene4Band \
    -f DateRangeFilter acquired gte 2019-01-27 \
    -f StringInFilter instrument PS2 \
    -f GeometryFilter C:\path\to\vectorfile.shp
```
To get the count for a set of filters without creating a search:
```
python create_saved_search.py --name my_search --item_types PSScene4Band \
    -f DateRangeFilter acquired gte 2019-01-27 \ 
    -f GeometryFilter C:\path\to\vectorfile.shp \
    --get_count \
    --dryrun
```
Once a search is successfully created, it will return a search ID. This can be used with 
select_imagery.py to create a footprint of the imagery:
```
python select_imagery.py -i [search ID] --out_path C:\path\to\write\footprint.shp
```



## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.