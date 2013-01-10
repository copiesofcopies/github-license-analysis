# -*- coding: utf-8 -*-
# TODO: DB storage, logging

import requests
import json
import optparse
import time
import yaml
import link_header
import re
import logging
import psycopg2
import sys
from urlparse import urljoin
from base64 import b64decode

config = None
requests_left = 60
license_pattern = re.compile(r"""\b(copying|license|gnu|gpl|apache|apl|bsd|cddl|
                                 mit|mozilla|mpl|eclipse|epl|qpl|isc)\b""",\
                                 re.IGNORECASE)

def get_repo(repo_url):
    r = api_request(repo_url)

    if(r.ok):
        repo_item = json.loads(r.text or r.content)
        return repo_item 

    return None

def get_repo_licenses(repo_url):
    global license_pattern
    license_files = {}

    base_url = "%s/contents/" % repo_url
    readme_url = "%s/readme" % repo_url

    # Iterate over files in TLD to look for license-ish filenames
    r = api_request(base_url)
    if(r.ok):
        base_dir = json.loads(r.text or r.content)

        # For each file...
        for afile in base_dir:
            if afile['type'] == 'file' and (not afile['name'] in license_files):

                # Run through each pattern...
                if license_pattern.search(afile['name']):
                    license_path = "%s%s" % (base_url, afile['name'])                    
                    file_r = api_request(license_path)
                    if(file_r.ok):
                        license_obj = json.loads(file_r.text or\
                                                     file_r.content)
                        license_files[afile['name']] = license_obj

    # Tack on the README file
    r = api_request(readme_url)
    if(r.ok):
        readme_file = json.loads(r.text or r.content)
        license_files[readme_file['name']] = readme_file

    return license_files

def api_request(url):
    global requests_left

    u = config['github_user'] 
    p = config['github_password']
    r = None

    if(u and p):
        r = requests.get(url, auth=(u, p))
    else:
        r = requests.get(url)

    if(r.ok):
        requests_left = r.headers['X-RateLimit-Remaining']

    return r

if __name__ == "__main__":
    # Parse the yaml config file
    config_file = open('config.yaml', 'r')
    config = yaml.load(config_file.read())

    # Initialize database connection
    db_conn = psycopg2.connect(database=config['database'], 
                           user=config['database_user'],
                           password=config['database_password'])    
    
    cur = db_conn.cursor()

    # Set up the command line argument parser
    parser = optparse.OptionParser()

    parser.add_option('-u', '--url',
                      action="store", dest="url",
                      help="""URL to begin retriving repositories with
                              ('next' link from last result)""",
                      default="")
    
    options, args = parser.parse_args()

    # Initialize log file
    logger = logging.getLogger(__name__)
    logging.basicConfig(filename='output.log',level=logging.ERROR)
    logging.getLogger(__name__).setLevel(logging.DEBUG)

    # Get the URL from the 'url' argument or start from square one
    repos_url = options.url or "https://api.github.com/repositories"
    next_repos_url = repos_url

    # Retrieve pages of repos till rate limit is reached
    r = api_request(next_repos_url)
    logger.info("Request status: %s" % r.headers['status'])

    while(r.ok):
        repos_json = json.loads(r.text or r.content)

        logger.info("Requests left: %s" % requests_left)

        # Get link for next page of repos
        links = link_header.parse_link_value(r.headers['link'])

        for link_url in links:
            if(links[link_url]['rel'] == 'next'):
                next_repos_url = link_url

        # Process this page of repos
        for repo in repos_json:

            # If we're out of requests, sleep in 5-minute increments
            while(requests_left < 4):
                logger.info("Waiting for rate limit to reset...")
                time.sleep(300)
                rl_resp = api_request("https://api.github.com/rate_limit")

            # Log the effort to store this repo's information:
            logger.info("Storing repository %s (Fork? %s)" % \
                            (repo['full_name'], repo['fork']))

            # Store repo in the DB
            try:
                cur.execute("""
                            INSERT INTO repositories(gh_id, owner_login, name,
                                        full_name, description, private, fork,
                                        api_url, html_url) VALUES (%s, %s, %s, 
                                        %s, %s, %s, %s, %s, %s)
                            """, (repo['id'], repo['owner']['login'],
                                  repo['name'], repo['full_name'],
                                  repo['description'], repo['private'], 
                                  repo['fork'], repo['url'],
                                  repo['html_url']))

                db_conn.commit()

                # Find likely license files
                licenses = get_repo_licenses(repo['url'])
                license_names = []

                for license_name in licenses:
                    license_names.append(license_name)
                    alicense = licenses[license_name]

                    logger.info("Storing license: %s" % license_name)

                    # Store this license in the DB
                    try:
                        cur.execute("""
                            INSERT INTO repository_licenses(repository_id,
                                        type, encoding, api_url, html_url,
                                        size, name, path, content, sha) VALUES (
                                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (repo['id'], alicense['type'], 
                                  alicense['encoding'], 
                                  alicense['_links']['self'],
                                  alicense['_links']['html'],
                                  alicense['size'], alicense['name'],
                                  alicense['path'], alicense['content'], 
                                  alicense['sha']))

                        db_conn.commit()
                    except psycopg2.DatabaseError, e:
                        db_conn.rollback()
    
                        logger.error('Error %s when adding file %s for repo %s' %\
                                         (e, license_name, repo['full_name']))    
                        db_conn.close()
                        sys.exit(1)

            except psycopg2.IntegrityError:

                # We've already got one -- rollback and hit the next one
                logger.info("Repository already retrieved, moving on...")
                db_conn.rollback()

            except psycopg2.DatabaseError, e:

                # Unhandled errors dump us 
                db_conn.rollback()
    
                logger.error('Error %s when inserting %s' % (e, repo['full_name']))    
                db_conn.close()
                sys.exit(1)

        # Get the next page of repos
        logger.info("Finished a page. Getting the next from %s" %\
            next_repos_url)

        r = api_request(next_repos_url)
        logger.info("Request status: %s" % r.headers['status'])
