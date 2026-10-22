#!/usr/bin/env python3
import argparse
import glob
import json
import logging

import requests
from boltons.iterutils import remap
from bs4 import BeautifulSoup

HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
HOST = "http://localhost:8000/"

logger = logging.getLogger(__name__)


def login(user, password):
    payload = {"username": user, "password": password}
    response = requests.post(
        HOST + "api/rest-auth/login/", headers=HEADERS, json=payload
    )
    token = response.json()["key"]
    return token


def run_upload(token, user):
    headers = HEADERS.copy()
    headers.update({"Authorization": f"Token {token}"})
    print(token)
    url = HOST + "/api/tool/validate/"
    # register tools
    tools_ok = []
    tools_ko = []
    for biotools_json_file in glob.glob("../content/data/*/*.biotools.json"):
        try:
            logger.debug(f"uploading {biotools_json_file}...")
            with open(biotools_json_file) as f:
                payload_dict = json.load(f)
            payload_dict["editPermission"]["authors"] = [user]
            payload_dict = remap(payload_dict, lambda p, k, v: k != "term")
            response = requests.post(url, headers=headers, json=payload_dict)
            response.raise_for_status()
            tools_ok.append(payload_dict["biotoolsID"])
            logger.debug(response.json())
            logger.debug(f"done uploading {biotools_json_file}")
        except requests.exceptions.HTTPError:
            if response.status_code == 500:
                soup = BeautifulSoup(response.text, "html.parser")
                messages = "; ".join(
                    [
                        ",".join(error_el.contents)
                        for error_el in soup.find_all(class_="exception_value")
                    ]
                )
            else:
                messages = response.text
            logger.error(
                f"error while uploading {biotools_json_file} (status {response.status_code}): {messages}"
            )
            tools_ko.append(payload_dict["biotoolsID"])
        except (FileNotFoundError, PermissionError) as e:
            logger.error(f"file error while uploading {biotools_json_file}: {e}")
            # Note: can't get biotoolsID if file couldn't be read
        except json.JSONDecodeError as e:
            logger.error(f"invalid JSON in {biotools_json_file}: {e}")
        except KeyError as e:
            logger.error(f"missing required field {e} in {biotools_json_file}")
            if "biotoolsID" in payload_dict:
                tools_ko.append(payload_dict["biotoolsID"])
        except requests.RequestException as e:
            logger.error(f"request error while uploading {biotools_json_file}: {e}")
            if "biotoolsID" in payload_dict:
                tools_ko.append(payload_dict["biotoolsID"])
        except Exception:
            logger.exception(f"unexpected error while uploading {biotools_json_file}")
            if "biotoolsID" in payload_dict:
                tools_ko.append(payload_dict["biotoolsID"])
    logger.info("Tools upload finished")
    logger.info(f"Tools OK: {len(tools_ok)}")
    logger.info(f"Tools KO: {len(tools_ko)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bulk upload github tools to a test bio.tools server"
    )
    parser.add_argument("login", type=str, help="bio.tools login")
    parser.add_argument("password", type=str, help="bio.tools password")
    args = parser.parse_args()
    token = login(args.login, args.password)
    run_upload(token, args.login)
