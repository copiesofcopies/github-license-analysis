# TODO: DB storage, logging

import requests
import json
import optparse
import time
import yaml
import link_header
from urlparse import urljoin
from base64 import b64decode

config = None

def get_repo(repo_url):
    r = api_request(repo_url)

    if(r.ok):
        repo_item = json.loads(r.text or r.content)
        return repo_item 

    return None

def get_repo_license(repo_url):
    license_files = {'COPYING':None, 'LICENSE':None, 'README':None}

    copying_url = "%s/contents/%s" % (repo_url, 'COPYING')
    license_url = "%s/contents/%s" % (repo_url, 'LICENSE')
    readme_url = "%s/readme" % repo_url

    r = api_request(copying_url)
    if(r.ok):
        copying_file = json.loads(r.text or r.content)
        license_files['COPYING'] = copying_file
    
    r = api_request(license_url)
    if(r.ok):
        license_file = json.loads(r.text or r.content)
        license_files['LICENSE'] = license_file

    r = api_request(readme_url)
    if(r.ok):
        readme_file = json.loads(r.text or r.content)
        license_files['README'] = readme_file

    return license_files

def api_request(url):
    u = config['github_user'] 
    p = config['github_password']

    if(u and p):
        return requests.get(url, auth=(u, p))
    else:
        return requests.get(url)

if __name__ == "__main__":
    # Parse the yaml config file
    config_file = open('config.yaml', 'r')
    config = yaml.load(config_file.read())

    # Set up the command line argument parser
    parser = optparse.OptionParser()

    parser.add_option('-u', '--url',
                      action="store", dest="url",
                      help="""URL to begin retriving repositories with
                              ('next' link from last result)""",
                      default="")
    
    options, args = parser.parse_args()

    # Get the URL from the 'url' argument or start from square one
    repos_url = options.url or "https://api.github.com/repositories"
    next_repos_url = repos_url

    # Retrieve pages of repos till rate limit is reached
    requests_left = 5000
    r = api_request(next_repos_url)

    while(r.ok):
        repos_json = json.loads(r.text or r.content)
        requests_left = r.headers['X-RateLimit-Remaining']

        # Get link for next page of repos
        links = link_header.parse_link_value(r.headers['link'])

        for link_url in links:
            if(links[link_url]['rel'] == 'next'):
                next_repos_url = link_url

        # Process this page of repos
        for repo in repos_json:
            # If we're out of requests, sleep in 5-minute increments
            while(requests_left < 4):
                print "Waiting for rate limit to reset..."
                time.sleep(300)
                rl_resp = api_request("https://api.github.com/rate_limit")
                if(rl_resp.ok):
                    requests_left = rl_resp.headers['X-RateLimit-Remaining']

            licenses = get_repo_license(repo['url'])

            print "Repository: %s\nFork? %s" % (repo['full_name'], repo['fork'])

            if(licenses['LICENSE']):
                print "LICENSE: %s" % licenses['LICENSE']['path']
            else:
                print "LICENSE: None"

            if(licenses['COPYING']):
                print "COPYING: %s" % licenses['COPYING']['path']
            else:
                print "COPYING: None"

            print ""
        
        # Get the next page of repos
        print "Finished with that batch! Getting the next from %s" %\
            next_repos_url

        r = api_request(next_repos_url)
