# 1. Install virtual enviroment
```pip install virtualenv```

Virutal Environment is like a folder on top of Python, where we can add 3rd-party
libraries specific to our project.

# 2. Create virtual environment
```python -m venv venv```

Activate virtual environment: specify the path to activate file
```venv/Scripts/activate``` -> has ```(venv)``` in front of shell prompt

*To re-enter the virtual environment, re-activate it.*

# 3. Install Scrapy
```pip install scrapy```

# 4. Create a Scrapy project
```scrapy startproject job_scraper``` -> home for different spiders of different websites
```cd job_scraper```

*If `import scrapy` causes an error, press F1 -> Python: Select Interpreter -> .\venv\Scripts\python.exe*

To define fields, go to `items.py` file.

# 5. Create Scrapy spider
```cd job_scraper/spiders```

```scrapy genspider <name> <domain>``` -> used for different websites, note that files in the home folder is used universally for all spiders, make sure to use CUSTOM_SETTINGS for each spider

```scrapy genspider jobspider https://www.topcv.vn/tim-viec-lam-moi-nhat```

Notes: 

A Python file named `jobspider.py` is created -> write the scraping code there.

```pip install ipython```

Go to `scrapy.cfg` and add this line `shell = ipython` 

```scrapy shell``` -> now we can see a list of command to extract the data from website (note that scripts must be without errors for this command to run)

To prvent `fetch(url)` from being prevented, do the following things

- ```pip install scrapy-user-agents```

- Configure `USER_AGENT`, `ROBOTSTXT_OBEY`, `DOWNLOAD_DELAY`, `DEFAULT_REQUEST_HEADERS`, `DOWNLOADER_MIDDLEWARES` as is in the `settings.py` file.

To interact with the website, use the variable `response`.

# 6. Saving data to file

- To save data to file via command line, run `scrapy crawl <scriptname> -o <filename>`

```scrapy crawl jobspider -o jobdata.json``` 

-> Use for testing

- To save data to file via `settings.py`, configure `FEEDS` as in the `settings.py`, and add this line of code in the script

```
custom_settings = {
    FEEDS : {
        f'jobdata_topcv{timestamp}.json':{'format':'json'}
    }
}
```

To save log of only important information, configure `LOG_FILE` and  `LOG_LEVEL` as in the `settings.py`.


# 7. User agents
Install scrapy user agents `pip install scrapy-user-agents`.
Configure `DOWNLOADER_MIDDLEWARES` as in `settings.py`.


# 8. Data Cleanings
First, go to `items.py` and define fields in it, this would make our script less vulnerable to errors.
Then, import the name of the function where we define these fields into the main script and modify the main script as is.
Go to `pipelines.py` and write the data-clening code there.
Remember to uncomment `ITEM_PIPELINES` in the settings file.
Run the scipt like usual and the data will be cleaned for us.

# 9. AWS
To connect Scrapy Shell to S3 bucket, configure `FEEDS`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`as is in `settings.py`. Install `botocore` also.

[For more instructions, follow this link](https://stackoverflow.com/questions/38788096/how-to-upload-crawled-data-from-scrapy-to-amazon-s3-as-csv-or-json)

To hide secret information, install `python-dotenv`, create the `.env` file and add the secret information there, and configure `load_env` as is in the `settings.py` file.

10. Incremental crawling

```pip install scrapy-deltafetch```

```DELTAFETCH_ENABLED = True``` remember crawled urls
 
```DELTAFETCH_ITEM_BASED = True``` an url is only marked finished only if the inside data is crawled

```overwrite=False in FEEDS``` append mode in the result file

SPIDER_MIDDLEWARES = {
   "science_dwh.middlewares.ScienceDwhSpiderMiddleware": 543,
   'scrapy_deltafetch.DeltaFetch': 100,
}

11. JOBDIR

JOBDIR only remembers urls crawl in a single crawl job, doesn't work between multilple jobs, to resume a crawl job, run this command:
```scrapy crawl <ten_>spider_name> -s JOBDIR=jobdir```

------
To install all packages for Scrapling, run:
```pip install "scrapling[all]"```

```scrapling install```


To run Scrapling in terminal:

```python # similar to scrapy shell environment```

```import```

