#!/bin/bash

xls_file=$1
file_prefix=$2
json_file="outputs/${file_prefix}.json"
brat_file="outputs/${file_prefix}_brat"
new_json="outputs/new_${file_prefix}.json"

echo "[Step1] convert xls file to json"
python format_converter.py \
--mode 'xls2json' \
--xls ${xls_file} \
--json ${json_file}

echo "[Step2] convert '所見' or 'findings' of json file to brat (200 reports per file)"
python format_converter.py \
--mode 'json2brat' \
--json ${json_file} \
--brat ${brat_file}

echo "[Step3] combine brat ann into json"
python format_converter.py \
--mode 'brat2json' \
--brat ${brat_file} \
--json ${json_file} \
--njson ${new_json}
