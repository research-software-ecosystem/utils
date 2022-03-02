#!/usr/bin/env python3

import os
import sys
import json
import jsonpatch
import urllib.request

TOOLS_CONTENT_PATH = "../../../content/data/"
OPENEBENCH_METRICS_ENDPOINT = "https://openebench.bsc.es/monitor/metrics/"

JSONPATH_FILTER = ['/@timestamp', '/project/website/last_check', '/project/website/access_time', '/project/website/last_month_access/', '/project/website/half_year_stat/']

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

  files_added = 0
  obj_added = 0
  obj_removed = 0
  prop_total = 0
  prop_changed = 0

  for tool_dir, m in git_metrics.items():
    path = tool_dir + '/' + os.path.basename(tool_dir) + '.oeb.metrics.json'
    if (os.path.isfile(path)):
      with open(path, 'r+') as f:
        old = {}
        try:
          for old_metrics in json.load(f):
            old[old_metrics.get('@id')] = old_metrics
        except Exception as ex:
          print('invalid json file: ', path, ' ', ex, file = sys.stderr)

        for new_metrics in m:
          prop_total += traverse(new_metrics)

          _id = new_metrics.get('@id')
          old_metrics = old.get(_id)
          if (old_metrics != None):
            patch = op_filter(jsonpatch.JsonPatch.from_diff(old_metrics, new_metrics).patch);
            prop_changed += len(patch);
            old.pop(_id) 
          else:
            obj_added += 1

        obj_removed += len(old)
    else:
      obj_added += len(m)
      files_added  += 1

    with open(path, 'w') as f:
      try:
        json.dump(m, f, indent=4, sort_keys=True)
      except Exception as ex:
        print('error writing file: ', path, ' ', ex, file = sys.stderr)

  print('{"add_files":"', files_added, '", "add_objects":"', obj_added, '", "remove_objects":"', obj_removed, '", "diff":"', (prop_changed / prop_total), '" }')

# Get OpenEBench metrics
def get_metrics():
  res = urllib.request.urlopen(OPENEBENCH_METRICS_ENDPOINT);
  if(res.getcode() < 300):
    data = res.read()
    return json.loads(data)

  print("error reading metrics", req) 

def op_filter(patch):
  for i, op in reversed(list(enumerate(patch))):
    path = op.get('path')
    for f in JSONPATH_FILTER:
      if (path.startswith(f)):
        patch.pop(i)
        break
  return patch

# count total number of properties in the (json) object
def traverse(obj):
  count = 1
  if isinstance(obj, dict):
    count = len(obj)  
    for val in obj.values():
      count += traverse(val)
  elif isinstance(obj, list):
    count = len(obj) 
    for val in obj:
      count += traverse(val)

  return count

if __name__ == "__main__":
    main()
