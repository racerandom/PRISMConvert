# coding: utf-8
import os
import json
import re
import math
import subprocess
from argparse import ArgumentParser
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import date, datetime
from textformatting import ssplit
import sys
sys.path.append("..")
import data_utils

tag2name = {
    'd': 'Disease',
    'a': 'Anatomical',
    'f': 'Feature',
    'c': 'Change',
    'p': 'Pending',
    'TIMEX3': 'TIMEX3',
    't-test': 'TestTest',
    't-key': 'TestKey',
    't-val': 'TestVal',
    'cc': 'ClinicalContext',
    'r': 'Remedy',
    'm-key': 'MedicineKey',
    'm-val': 'MedicineVal',
}

name2tag = {v:k for k,v in tag2name.items()}


def fix_finding_str(finding_str):
    finding_str = finding_str.replace('\r</', '</')
    finding_str = finding_str.replace('\n</', '</')
    finding_str = finding_str.replace('＜', '&lt;')
    finding_str = finding_str.replace('＞', '&gt;')
    return finding_str


def fix_xml_str(xml_str):
    xml_str = xml_str.replace('<代理診察>', '《代理診察》')
    xml_str = xml_str.replace('<胸部CT>', '《胸部CT》')
    xml_str = xml_str.replace('<胸部単純CT>', '《胸部単純CT》')
    xml_str = xml_str.replace('<ABD US>', '《ABD US》')
    xml_str = xml_str.replace('<CHEST>', '《CHEST》')
    xml_str = xml_str.replace('<CHEST；CT>', '《CHEST；CT》')
    xml_str = xml_str.replace('<CHEST;CT>', '《CHEST；CT》')
    xml_str = xml_str.replace('<CHEST: CT>', '《CHEST: CT》')
    xml_str = xml_str.replace('<Liver>', '《Liver》')
    xml_str = xml_str.replace('<経過>', '《経過》')
    xml_str = xml_str.replace('<カンファレンスのpoint>', '《カンファレンスのpoint》')
    xml_str = xml_str.replace(', correction=', ' correction=')
    xml_str = xml_str.replace('<長期経過>', '《長期経過》')
    xml_str = xml_str.replace('<予習>', '《予習》')
    xml_str = xml_str.replace('<L/D>', '《L/D》')
    xml_str = xml_str.replace('&', '&amp;')
    xml_str = xml_str.replace('<<', '<')
    xml_str = xml_str.replace('>>', '>')
    xml_str = xml_str.replace('="suspicious>', '="suspicious">')
    return xml_str

# def escape_xml_str(xml_str):
#     xml_str = xml_str.replace('<', '&lt;')
#     xml_str = xml_str.replace('>', '&gt;')
#     xml_str = xml_str.replace('&', '&amp;')
#     return xml_str


def read_xls(xls_file):
    json_dict = {}
    json_dict['読影所見'] = {}
    json_dict['文章名'] = xls_file.split('/')[-1]

    if xls_file.endswith('csv'):
        df = pd.read_csv(xls_file, index_col=None, date_parser=None, encoding='utf-8').fillna('')
    elif xls_file.endswith('xlsx'):
        df = pd.read_excel(xls_file, index_col=None, sheet_name=0, date_parser=None).fillna('')
    else:
        raise Exception('[ERROR] Unsupported excel file')

    for row_index, row in df.iterrows():
        row_dict = {}
        for col_name in row.keys():
            row_dict[col_name] = row[col_name]
            json_dict['読影所見'][str(row_index + 1)] = row_dict
    return json_dict


def dump_json(dict_data, json_file):

    def json_serial(obj):
        # 日付型の場合には、文字列に変換します
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        # 上記以外はサポート対象外.
        raise TypeError("Type %s not serializable" % type(obj))

    with open(json_file, 'w', encoding='utf-8') as json_fo:
        json_fo.write(json.dumps(dict_data, indent=2, ensure_ascii=False, default=json_serial))


def split_sent_to_xml(text, head_line):
    """ execute outside sentence-splitter code """
    with open('tmp.txt', 'w', encoding='utf-8') as fo:
        fo.write(text)
    script = '''cat tmp.txt | perl -I sentence-splitter.pl | python split_tnm.py  > tmp.sent'''
    subprocess.Popen(script, shell=True).wait()
    with open('tmp.sent', 'r', encoding='utf-8') as fi:
        xml_str = '<doc>\n' + \
                  '<line>%s</line>\n' % head_line + \
                  '\n'.join(['<line>' + line.strip() + '</line>' for line in fi]) + '\n</doc>\n'
    return xml_str


def extract_txt_from_xls(xls_file, txt_file, split_sent=True, segment=True):
    from pyknp import Juman
    import mojimoji
    juman = Juman()

    json_dict = read_xls(xls_file)
    tmp_file = txt_file if not split_sent else 'tmp.raw'
    with open(tmp_file, 'w', encoding="utf-8") as fo:
        for report in json_dict['読影所見'].values():
            fo.write('%s\n' % report['findings'])
    if split_sent:
        script = '''cat tmp.raw | perl sentence-splitter.pl | python split_tnm.py  > tmp.sent'''
        subprocess.Popen(script, shell=True).wait()
    if segment:
        with open('tmp.sent', 'r', encoding='utf-8') as fi, open(txt_file, 'w', encoding='utf-8') as fo:
            for line in fi:
                unspace_line = ''.join(line.strip().split())
                if not unspace_line:
                    continue
                seg_line = ' '.join([w.midasi for w in juman.analysis(mojimoji.han_to_zen(unspace_line)).mrph_list()])
                fo.write('%s\n' % seg_line)
    os.remove('tmp.raw')
    os.remove('tmp.sent')


def convert_xml_to_brat(xml_file, output_dir='data/tmp'):
    doc_toks, mention_offsets = [], []
    tmp_offset = 0
    root = ET.parse(xml_file).getroot()
    for text_node in root.findall('TEXT'):
        for sent_node in text_node.iter('sentence'):
            for tag in sent_node.iter():
                try:
                    if tag.text and tag.text.strip():
                        char_seg = list(tag.text.strip())
                        doc_toks += char_seg
                        if tag.tag in ['EVENT', 'event'] and 'eid' in tag.attrib:
                            mention_offsets.append((tag.attrib['eid'], 'EVENT', tmp_offset, tmp_offset + len(char_seg), tag.text.strip()))
                        elif tag.tag in ['TIMEX3'] and 'tid' in tag.attrib:
                            mention_offsets.append((tag.attrib['tid'], 'TIMEX3', tmp_offset, tmp_offset + len(char_seg), tag.text.strip()))
                        tmp_offset += len(char_seg)
                    if tag.tag != 'sentence' and tag.tail and tag.tail.strip():
                        char_seg = list(tag.tail.strip())
                        doc_toks += char_seg
                        tmp_offset += len(char_seg)
                except Exception as ex:
                    print('[ERROR]', ex)
            if len(doc_toks) > 1:
                if not (doc_toks[-1] == '\n'):
                    doc_toks += ['\n']
                    tmp_offset += 1
            else:
                doc_toks += ['\n']
                tmp_offset += 1
    output_file = '%s/%s' % (output_dir, xml_file.split('/')[-1].split('.')[0])
    with open('%s.txt' % output_file, 'w') as fot:
        fot.write('%s' % (''.join(doc_toks)))

    with open('%s.ann' % output_file, 'w') as foa:
        for mid, mtype, offs_b, offs_e, m in mention_offsets:
            assert ''.join([doc_toks[i] for i in range(offs_b, offs_e)]) == m
            foa.write('%s\t%s\t%i\t%i\t%s\n' % (mid, mtype, offs_b, offs_e, m))


def extract_normtime_from_json(json_file, normtime_file):
    import mojimoji

    with open(json_file) as json_fi:
        json_dict = json.load(json_fi)
        pid_to_print = None
        pdate_to_print = None
        present_lines = []
        for line_id, instance in json_dict['読影所見'].items():

            if 'ann' not in instance or not instance['タイトル']:
                continue

            present_id = str(instance['表示順'])
            present_date = str(instance['記載日']).split('T')[0]

            if pid_to_print and present_id != pid_to_print:
                out_file = f"{normtime_file}_{pid_to_print}_{pdate_to_print}.txt"
                with open(out_file, 'w', encoding='utf8') as fo:
                    for out_line in present_lines:
                        fo.write(out_line)
                print(f"output file: {out_file}...")
                present_lines = []

            pid_to_print = present_id
            pdate_to_print = present_date

            head_items = []
            head_items.append(f"line id: {line_id}")
            head_items.append(f"表示順: {present_id}")
            patient_id = str(instance['匿名ID'])
            head_items.append(f"匿名ID: {patient_id}")
            head_items.append(f"タイトル: {instance['タイトル'].strip()}")
            head_items.append(f"記載日: {present_date}")
            head_line = f"## {' ||| '.join(head_items)}"

            finding = instance['ann']
            # finding = '\n'.join(ssplit(finding))
            xml_str = '<doc>\n' + \
                      '<s>%s</s>\n' % head_line + \
                      '\n'.join(['<s>' + line.strip() + '</s>' for line in finding.split('\n')]) + '\n</doc>\n'
            # xml_str = "<doc><s><a>sjdf</a>sdf</s></doc>"
            xml_str = fix_xml_str(xml_str)
            # print(xml_str)
            try:
                root = ET.ElementTree(ET.fromstring(xml_str)).getroot()
                for sent_node in root.iter('s'):
                    sent_text, timex_list, char_index = [], [], 0
                    for tag in sent_node.iter():

                        if tag.text:
                            text_char = list(tag.text.replace('\n', ''))
                            sent_text.append(''.join(text_char))

                            if tag.tag == 'TIMEX3':
                                timex_entry = f"\t{char_index}\t{char_index + len(text_char)}\t{tag.attrib['type']}\n"
                                timex_list.append(timex_entry)
                            char_index += len(text_char)

                        if tag.tail:
                            tail_char = list(tag.tail.replace('\n', ''))
                            sent_text.append(''.join(tail_char))
                            char_index += len(tail_char)

                    present_lines.append(f"{''.join(sent_text)}\n")
                    for t in timex_list:
                        present_lines.append(t)
                    present_lines.append('\n')

            except Exception as ex:
                print('[ERROR] line number：', line_id)
                print(ex)
                print(xml_str)

        if pid_to_print:
            out_file = f"{normtime_file}_{pid_to_print}_{pdate_to_print}.txt"
            with open(out_file, 'w', encoding='utf8') as fo:
                for out_line in present_lines:
                    fo.write(out_line)
            print(f"output file: {out_file}...")


def extract_brat_from_json(json_file, brat_file, corpus,
                           rid_col, pid_col, date_col, type_col, ann_col,
                           sent_split=False):
    import mojimoji

    with open(json_file) as json_fi:
        json_dict = json.load(json_fi)
        char_toks, tags, attrs = [], [], []
        char_offset, tag_offset, attr_offset = 0, 1, 1
        prev_delimiter_flag = None
        for line_id, instance in json_dict['読影所見'].items():

            '''
            comment line: ## line id: 1 ||| 表示順: 1 ||| 匿名ID: 3276171 ||| タイトル: S ||| 記載日: 2014-03-20
            '''
            line_id = int(line_id)
            comment_items = [f"line id: {line_id}"]

            patient_id = str(instance[pid_col]).strip()
            report_id = str(instance[rid_col])
            curr_delimiter_flag = report_id
            comment_items.append(f"表示順: {curr_delimiter_flag}")

            # print(line_id, report_id)

            if not prev_delimiter_flag:
                prev_delimiter_flag = curr_delimiter_flag

            if tags and curr_delimiter_flag != prev_delimiter_flag:

                out_rid = f"表示順{prev_delimiter_flag}"

                with open(f'{brat_file}.{out_rid}.txt', 'w') as fot:
                    fot.write('%s' % (''.join(char_toks)))

                with open(f'{brat_file}.{out_rid}.ann', 'w') as foa:
                    for tid, ttype, char_b, char_e, t in tags:
                        foa.write('%s\t%s %s %s\t%s\n' % (
                            tid,
                            tag2name[ttype],
                            char_b,
                            char_e,
                            t
                        ))

                    for aid, key, tid, value in attrs:

                        if key != 'tid':
                            foa.write('%s\t%s %s %s\n' % (
                                aid,
                                key,
                                tid,
                                value
                            ))
                print('Converted json to brat, 表示順: %s processed.' % prev_delimiter_flag)

                # reset caches
                char_toks, tags, attrs = [], [], []
                char_offset, tag_offset, attr_offset = 0, 1, 1
                prev_delimiter_flag = curr_delimiter_flag

            if ann_col not in instance:
                continue
            finding = instance[ann_col]
            finding = fix_finding_str(finding)

            comment_items.append(f"匿名ID: {patient_id}")

            if type_col in instance:
                if instance[type_col].strip() in ['I']:
                    continue
                comment_items.append("タイトル: %s" % instance['タイトル'].strip())

            comment_items.append(f"記載日: {str(instance[date_col]).split('T')[0]}")
            head_line = "## %s" % ' ||| '.join(comment_items)

            if sent_split:
                xml_str = split_sent_to_xml(finding, head_line)
            else:
                if corpus in ['ou', 'ncc']:
                    finding = '\n'.join(ssplit(mojimoji.zen_to_han(finding, kana=False)))
                xml_str = '<doc>\n' + \
                          (f'<line>{head_line}</line>\n' if corpus in ['mr'] else '') + \
                          '\n'.join([f'<line>{line.strip()}</line>' for line in finding.split('\n')]) + '\n</doc>\n'

            xml_str = fix_xml_str(xml_str)
            tmp_char_toks, tmp_tags, tmp_attrs = [], [], []
            tmp_char_offset, tmp_tag_offset, tmp_attr_offset = char_offset, tag_offset, attr_offset
            try:
                root = ET.ElementTree(ET.fromstring(xml_str)).getroot()
                for sent_node in root.iter('line'):
                    for tag in sent_node.iter():
                        if tag.text:
                            char_seg = list(tag.text)
                            tmp_char_toks += char_seg
                            if tag.tag != 'line':
                                tmp_tags.append((
                                    'T%i' % tmp_tag_offset,
                                    tag.tag,
                                    tmp_char_offset,
                                    tmp_char_offset + len(char_seg),
                                    tag.text
                                ))
                                if tag.attrib:
                                    for key, value in tag.attrib.items():
                                        tmp_attrs.append((
                                            'A%i' % tmp_attr_offset,
                                            key,
                                            'T%i' % tmp_tag_offset,
                                            value
                                        ))
                                        tmp_attr_offset += 1
                                tmp_tag_offset += 1
                            tmp_char_offset += len(char_seg)
                        if tag.tag != 'line' and tag.tail:
                            char_seg = list(tag.tail)
                            tmp_char_toks += char_seg
                            tmp_char_offset += len(char_seg)
                    if len(tmp_char_toks) > 1:
                        if not (tmp_char_toks[-1] == '\n'):
                            tmp_char_toks += ['\n']
                            tmp_char_offset += 1
                    else:
                        tmp_char_toks += ['\n']
                        tmp_char_offset += 1
                char_toks += tmp_char_toks
                tags += tmp_tags
                attrs += tmp_attrs
                char_offset, tag_offset, attr_offset = tmp_char_offset, tmp_tag_offset, tmp_attr_offset
                for tid, ttype, char_b, char_e, t in tmp_tags:
                    assert ''.join([char_toks[i] for i in range(char_b, char_e)]) == t

            except Exception as ex:
                print(f'[ERROR] line number：{line_id}, rid: {report_id}')
                print(ex)
                print(xml_str)
                print()
                print(tmp_char_toks)
                print()
                for tid, ttype, char_b, char_e, t in tmp_tags:
                    print(char_b, char_e, ''.join([char_toks[i] for i in range(char_b, char_e)]), t)
                print()

            if line_id == len(json_dict['読影所見']) and char_toks:
                out_rid = f"表示順{curr_delimiter_flag}"

                with open(f'{brat_file}.{out_rid}.txt', 'w') as fot:
                    fot.write('%s' % (''.join(char_toks)))

                with open(f'{brat_file}.{out_rid}.ann', 'w') as foa:
                    for tid, ttype, char_b, char_e, t in tags:
                        foa.write('%s\t%s %s %s\t%s\n' % (
                            tid,
                            tag2name[ttype],
                            char_b,
                            char_e,
                            t
                        ))

                    for aid, key, tid, value in attrs:
                        if key != 'tid':
                            foa.write('%s\t%s %s %s\n' % (
                                aid,
                                key,
                                tid,
                                value
                            ))
                print('Converted json to brat, 表示順: %s processed.' % prev_delimiter_flag)


def combine_brat_to_json(json_file, brat_file, new_json):
    from collections import defaultdict
    with open(json_file, 'r') as json_fi:
        json_dict = json.load(json_fi)

        brat_dir, brat_name = os.path.split(brat_file)
        brat_file_list = set([os.path.join(brat_dir, '.'.join(filename.split('.')[:-1])) for filename in sorted(os.listdir(brat_dir)) if filename.startswith(brat_name)])

        for file_name in brat_file_list:
            print(file_name)
            # if file_name != "data/brat/sample001":
            #     continue
            # print(file_name)
            tid2cert, cid2tag, rid2rels = {}, {}, defaultdict(list)
            ann_filename = '%s.ann' % file_name
            if os.path.isfile(ann_filename):
                with open(ann_filename, 'r') as ann_fi:

                    for entity_line in ann_fi:
                        try:
                            entity_line = entity_line.strip()
                            if entity_line.startswith('T'):
                                tid, tag_type, b_cid, e_cid, surf = entity_line.split(None, 4)
                                cid2tag['s' + b_cid] = (tid, tag_type)
                                cid2tag['e' + e_cid] = (tid, tag_type)
                            elif entity_line.startswith('A'):
                                mod_id, mod_type, entity_id, mod_label = entity_line.split()
                                if mod_type in ['certainty', 'state', 'type']:
                                    tid2cert[entity_id] = (mod_type, mod_label)
                                elif mod_type in ['DCT-Rel']:
                                    rid2rels[entity_id].append((entity_id, entity_id, mod_label))
                                else:
                                    print("[error]", mod_type)
                            elif entity_line.startswith('R'):
                                rel_id, rel, tail_id, head_id = entity_line.split()
                                rid2rels[rel_id].append((tail_id.split(':')[-1], head_id.split(':')[-1], rel))
                        except Exception as ex:
                            print(ex)
                            print(entity_line)

            with open('%s.txt' % file_name, 'r') as txt_fi:
                char_list = list(txt_fi.read())
                ''' writing raw_text to json'''
                raw_str = ''.join(char_list)
                line_id, patient_id = None, None
                line_cache = []
                for line in raw_str.split('\n'):
                    z = re.match(r"## line id: (\w+)", line)
                    if z:
                        if line_id in json_dict['読影所見']:
                            json_dict['読影所見'][line_id]["raw_text"] = '\n'.join(line_cache)
                        line_id = z.groups()[0]
                        line_cache = []
                    else:
                        line_cache.append(line)
                if line_id in json_dict['読影所見']:
                    json_dict['読影所見'][line_id]["raw_text"] = '\n'.join(line_cache)

                ''' writing new_ann to json'''
                for key in sorted(cid2tag.keys(), key=lambda x: (int(x[1:]), x[0]), reverse=True):
                    cid = int(key[1:])
                    tid, tag_type = cid2tag[key]
                    # print(key, tag_type)
                    if key.startswith('e'):
                        char_list.insert(cid, '</%s>' % (name2tag[tag_type]))
                    elif key.startswith('s'):
                        elems = [name2tag[tag_type]]
                        elems.append('tid="%s"' % tid)
                        if tid in tid2cert:
                            elems.append('%s="%s"' % tid2cert[tid])
                        char_list.insert(cid, '<%s>' % (' '.join(elems)))

                txt_line = ''.join(char_list)
                line_id, patient_id = None, None
                line_cache = []
                for line in txt_line.split('\n'):
                    z = re.match(r"## line id: (\w+)", line)
                    if z:
                        if line_id in json_dict['読影所見']:
                            json_dict['読影所見'][line_id]["ann"] = '\n'.join(line_cache)
                            json_dict['読影所見'][line_id]["rels"] = '\n'.join([str(r) for rels in rid2rels.values() for r in rels])
                        line_id = z.groups()[0]
                        line_cache = []
                    else:
                        line_cache.append(line)

                if line_id in json_dict['読影所見']:
                    json_dict['読影所見'][line_id]["ann"] = '\n'.join(line_cache)
                    json_dict['読影所見'][line_id]["rels"] = '\n'.join([str(r) for rels in rid2rels.values() for r in rels])
        dump_json(json_dict, new_json)


def convert_bio_to_xml(bio_file, xml_file):
    with open(bio_file, 'r') as fi, open(xml_file, 'w') as fo:
        tmp_report_xml = ""
        prev_bio_tag = "O"
        for line in fi:
            token, bio_tag, cert_tag = line.split()
            if token != "EOR":
                if bio_tag.startswith('B'):
                    if prev_bio_tag != "O":
                        tmp_report_xml += "</%s>" % prev_bio_tag.split('-')[-1].lower()
                    tmp_report_xml += "<%s%s>%s" % (
                        bio_tag.split('-')[-1].lower(),
                        " certainty=\"%s\"" % cert_tag if cert_tag != '_' else "",
                        token
                    )
                elif bio_tag.startswith('I'):
                    if prev_bio_tag != "O":
                        if prev_bio_tag.split('-')[-1] != bio_tag.split('-')[-1]:
                            tmp_report_xml += "</%s>" % prev_bio_tag.split('-')[-1].lower()
                            tmp_report_xml += "<%s>%s" % (
                                bio_tag.split('-')[-1].lower(),
                                token
                            )
                        else:
                            tmp_report_xml += token
                    else:
                        tmp_report_xml += "<%s>%s" % (
                            bio_tag.split('-')[-1].lower(),
                            token
                        )
                else:
                    if prev_bio_tag != "O":
                        tmp_report_xml += "</%s>" % prev_bio_tag.split('-')[-1].lower()
                    tmp_report_xml += token
                prev_bio_tag = bio_tag
            else:
                fo.write(tmp_report_xml.replace('#', '') + '\n')
                fo.write('\n')
                tmp_report_xml = ""
                prev_bio_tag = "O"


parser = ArgumentParser(description='Convert xls 読影所見 to the json format')
parser.add_argument("--mode", dest="mode",
                    help="convert_mode, i.e. xls2txt, xls2json, json2brat and brat2json", metavar="CONVERT_MODE")
parser.add_argument("--corpus",
                    help="corpus: ncc, ou, mr", metavar="CORPUS")
parser.add_argument("--xls", dest="xls_file",
                    help="input excel file", metavar="INPUT_FILE")
parser.add_argument("--json", dest="json_file",
                    help="output excel file", metavar="OUTPUT_FILE")
parser.add_argument("--brat", dest="brat_file",
                    help="output brat txt and ann files", metavar="ANNOTATION_FILE")
parser.add_argument("--bio", dest="bio_file",
                    help="input bio file", metavar="BIO_FILE")
parser.add_argument("--txt", dest="txt_file",
                    help="output raw file", metavar="TXT_FILE")
parser.add_argument("--xml", dest="xml_file",
                    help="output xml file", metavar="XML_FILE")
parser.add_argument("--njson", dest="new_json",
                    help="output new json", metavar="OUTPUT_FILE")
parser.add_argument("--conll", dest="conll_file",
                    help="conll file", metavar="CONLL_FILE")
parser.add_argument("--norm", dest="normtime_file",)
args = parser.parse_args()

if args.mode in 'xls2json':
    finding_json = read_xls(args.xls_file)
    dump_json(finding_json, args.json_file)
elif args.mode in 'xls2txt':
    extract_txt_from_xls(args.xls_file, args.txt_file)
elif args.mode == 'json2brat':
    if args.corpus in ['mr']:
        extract_brat_from_json(args.json_file, args.brat_file, args.corpus,
                               rid_col='表示順', pid_col='匿名ID',
                               date_col='記載日', type_col='タイトル', ann_col='ann',
                               sent_split=False)
    elif args.corpus in ['ou']:
        extract_brat_from_json(args.json_file, args.brat_file, args.corpus,
                               rid_col='表示順', pid_col='匿名ID',
                               date_col='検査実施日', type_col='タイトル', ann_col='所見',
                               sent_split=False)
    elif args.corpus in ['ncc']:
        extract_brat_from_json(args.json_file, args.brat_file, args.corpus,
                               rid_col='ID', pid_col='_id',
                               date_col='exam_date', type_col='タイトル', ann_col='findings_demasked',
                               sent_split=False)
    else:
        raise Exception(f"Uknown corpus {args.corpus}")
elif args.mode == 'brat2json':
    combine_brat_to_json(args.json_file, args.brat_file, args.new_json)
elif args.mode == 'bio2xml':
    convert_bio_to_xml(args.bio_file, args.xml_file)
elif args.mode == 'conll2brat':
    doc_conll = data_utils.MultiheadConll(args.conll_file)
    doc_conll.doc_to_brat(args.brat_file)
elif args.mode == 'conll2xml':
    doc_conll = data_utils.MultiheadConll(args.conll_file)
    doc_conll.doc_to_xml(args.xml_file)
elif args.mode == 'json2norm':
    extract_normtime_from_json(args.json_file, args.normtime_file)


