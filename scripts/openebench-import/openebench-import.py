#!/usr/bin/env python3

import os
import json
import urllib.request

TOOLS_CONTENT_PATH = "../../../data/"
OPENEBENCH_METRICS_ENDPOINT = "https://openebench.bsc.es/monitor/metrics/"

def main():

  # dictionary to group metrics by the tool i.e. {'trimal' : [json1, json2, json3]}
  git_metrics = {}
  metrics = get_metrics()

  for m in metrics:
    uri = m.get('@id')
    suffix = uri.find('/', len(OPENEBENCH_METRICS_ENDPOINT))
    identifier = uri[len(OPENEBENCH_METRICS_ENDPOINT):] if suffix < 0 else uri[len(OPENEBENCH_METRICS_ENDPOINT):suffix]
    tokens = identifier.split(':');
    oeb_id = tokens[0] if len(tokens) == 1 else tokens[1]
    tool_dir = TOOLS_CONTENT_PATH + oeb_id

    if (tool_dir != None and os.path.isdir(tool_dir)):
      metrics_list = git_metrics.get(tool_dir)
      if (metrics_list != None):
        metrics_list.append(m)
      else:
        git_metrics[tool_dir] = [m]

  for tool_dir, m in git_metrics.items():
    with open(tool_dir + '/' + os.path.basename(tool_dir) + '.oeb.metrics.json', 'w') as f:
      json.dump(m, f)

# Get OpenEBench metrics
def get_metrics():
  res = urllib.request.urlopen(OPENEBENCH_METRICS_ENDPOINT);
  if(res.getcode() < 300):
    data = res.read()
    return json.loads(data)

  print("error reading metrics", req) 

if __name__ == "__main__":
    main()