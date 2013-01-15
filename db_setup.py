# Creates a simple postgres DB to store the GH data in
#
#!/usr/bin/python
# -*- coding: utf-8 -*-

import psycopg2
import sys
import yaml

con = None

# Parse the yaml config file
config_file = open('config.yaml', 'r')
config = yaml.load(config_file.read())

try:
     
    con = psycopg2.connect(database=config['database'], 
                           user=config['database_user'],
                           password=config['database_password'])    
    
    cur = con.cursor()
  
    cur.execute("""CREATE TABLE repositories(id SERIAL PRIMARY KEY, 
                                     gh_id INT UNIQUE,
                                     owner_login VARCHAR,
                                     name VARCHAR,
                                     full_name VARCHAR,
                                     description VARCHAR,
                                     private BOOLEAN,
                                     fork BOOLEAN,
                                     api_url VARCHAR,
                                     html_url VARCHAR)""")

    cur.execute("""CREATE TABLE repository_licenses(id SERIAL PRIMARY KEY, 
                                     repository_id INT REFERENCES repositories (gh_id),
                                     type VARCHAR,
                                     encoding VARCHAR,
                                     api_url VARCHAR,
                                     html_url VARCHAR,
                                     size INT,
                                     name VARCHAR,
                                     path VARCHAR,
                                     content TEXT,
                                     sha VARCHAR)""")

    cur.execute("""CREATE TABLE license_metadata(id SERIAL PRIMARY KEY, 
                                     license_id INT UNIQUE REFERENCES repository_licenses (id),
                                     stripped_sha VARCHAR,
                                     is_primary BOOL DEFAULT FALSE,
                                     license_abbr VARCHAR)""")

    con.commit()
    

except psycopg2.DatabaseError, e:
    
    if con:
        con.rollback()
    
    print 'Error %s' % e    
    sys.exit(1)
    
    
finally:
    
    if con:
        con.close()
