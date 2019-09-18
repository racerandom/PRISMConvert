# coding: utf-8
import os, json, re
import math
import subprocess
from argparse import ArgumentParser
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import date, datetime

tag2name = {
    'd': 'Disease',
    'a': 'Anatomical',
    'f': 'Feature',
    'c': 'Change',
    'p': 'Pending'
}

name2tag = {v:k for k,v in tag2name.items()}


def fix_finding_str(finding_str):
    finding_str = finding_str.replace('\r</', '</')
    finding_str = finding_str.replace('\n</', '</')
    return finding_str


def fix_xml_str(xml_str):
    xml_str = xml_str.replace('<胸部CT>', '《胸部CT》')
    xml_str = xml_str.replace('<胸部単純CT>', '《胸部単純CT》')
    xml_str = xml_str.replace('<ABD US>', '《ABD US》')
    xml_str = xml_str.replace('<CHEST>', '《CHEST》')
    xml_str = xml_str.replace('<CHEST；CT>', '《CHEST；CT》')
    xml_str = xml_str.replace('<CHEST: CT>', '《CHEST: CT》')
    xml_str = xml_str.replace('<Liver>', 'Liver')
    xml_str = xml_str.replace(', correction=', ' correction=')
    xml_str = xml_str.replace('<<a', '<a')
    xml_str = xml_str.replace('</a>>', '</a>')
    xml_str = xml_str.replace('<<d', '<d')
    xml_str = xml_str.replace('</d>>', '</d>')
    xml_str = xml_str.replace('<<f', '<f')
    xml_str = xml_str.replace('</f>>', '</f>')
    xml_str = xml_str.replace('<<c', '<c')
    xml_str = xml_str.replace('</c>>', '</c>')
    xml_str = xml_str.replace('="suspicious>', '="suspicious">')
    return xml_str


def read_xls(xls_file):
    json_dict = {}
    json_dict['読影所見'] = {}
    json_dict['文章名'] = xls_file.split('/')[-1]

    if xls_file.endswith('csv'):
        df = pd.read_csv(xls_file, index_col=None, date_parser=None, encoding='shift_jis').fillna('')
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
    with open('tmp.txt', 'w') as fo:
        fo.write(text)
    script = '''cat tmp.txt | perl sentence-splitter.pl | python split_tnm.py > tmp.sent'''
    subprocess.Popen(script, shell=True).wait()
    with open('tmp.sent') as fi:
        xml_str = '<doc>\n' + \
                  '<line>%s</line>\n' % head_line + \
                  '\n'.join(['<line>' + line.strip() + '</line>' for line in fi]) + '\n</doc>\n'
    return xml_str


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


def extract_brat_from_json(json_file, brat_file, line_delimiter=200):
    with open(json_file) as json_fi:
        json_dict = json.load(json_fi)
        char_toks, tags, attrs = [], [], []
        char_offset, tag_offset, attr_offset = 0, 1, 1
        for line_id, instance in json_dict['読影所見'].items():

            line_id = int(line_id)
            # if line_id != '1':
            #     continue
            patient_id = str(instance['匿名ID' if '匿名ID' in instance else 'ID'])
            finding = instance['所見' if '所見' in instance else 'findings']
            finding = fix_finding_str(finding)
            head_line = "## line id: %i ||| 匿名ID: %s" % (line_id, patient_id)
            xml_str = split_sent_to_xml(finding, head_line)
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
                                    tag.text.strip()
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
                print('[ERROR] line number：', line_id)
                print(ex)
                print(xml_str)
                print()
                print(tmp_char_toks)
                print()
                for tid, ttype, char_b, char_e, t in tmp_tags:
                    print(char_b, char_e, ''.join([char_toks[i] for i in range(char_b, char_e)]), t)
                print()

            if line_id % line_delimiter == 0 or line_id == len(json_dict['読影所見']):

                index_range_str = '%i-%i' % (100 * (math.ceil(line_id / 100) - int(line_delimiter / 100)) + 1, line_id)

                with open('%s.%s.txt' % (brat_file, index_range_str), 'w') as fot:
                    fot.write('%s' % (''.join(char_toks)))

                with open('%s.%s.ann' % (brat_file, index_range_str), 'w') as foa:
                    for tid, ttype, char_b, char_e, t in tags:
                        # assert ''.join([char_toks[i] for i in range(offs_b, offs_e)]) == t
                        foa.write('%s\t%s %s %s\t%s\n' % (
                            tid,
                            tag2name[ttype],
                            char_b,
                            char_e,
                            t
                        ))

                    for aid, key, tid, value in attrs:
                        # assert ''.join([char_toks[i] for i in range(offs_b, offs_e)]) == t
                        foa.write('%s\t%s %s %s\n' % (
                            aid,
                            key,
                            tid,
                            value
                        ))

                char_toks, tags, attrs = [], [], []
                char_offset, tag_offset, attr_offset = 0, 1, 1

                print('Converted json to brat, number of line processed: %s' % line_id)


def combine_brat_to_json(json_file, brat_file, new_json):
    with open(json_file, 'r') as json_fi:
        json_dict = json.load(json_fi)

        brat_dir, brat_name = brat_file.split('/')
        brat_file_list = set([os.path.join(brat_dir, '.'.join(filename.split('.')[:2])) for filename in sorted(os.listdir(brat_dir)) if filename.startswith(brat_name)])
        for file_name in brat_file_list:
            with open('%s.txt' % file_name, 'r') as txt_fi, open('%s.ann' % file_name, 'r') as ann_fi:
                tid2cert, cid2tag = {}, {}
                for entity_line in ann_fi:
                    entity_line = entity_line.strip()
                    if entity_line.startswith('T'):
                        tid, tag_type, b_cid, e_cid, surf = entity_line.split(None, 4)
                        cid2tag['b' + b_cid] = (tid, tag_type)
                        cid2tag['e' + e_cid] = (tid, tag_type)
                    elif entity_line.startswith('A'):
                        aid, cert, tid, cert_type = entity_line.split(None, 3)
                        tid2cert[tid] = cert_type

                char_list = list(txt_fi.read())

                ''' writing raw_text to json'''
                raw_str = ''.join(char_list)
                line_id, patient_id = None, None
                line_cache = []
                for line in raw_str.split('\n'):
                    z = re.match(r"## line id: (\w+) \|\|\| 匿名ID: (\w+)", line)
                    if z:
                        if line_id in json_dict['読影所見']:
                            json_dict['読影所見'][line_id]["raw_text"] = '\n'.join(line_cache)
                        line_id, patient_id = z.groups()
                        line_cache = []
                    else:
                        line_cache.append(line)
                if line_id in json_dict['読影所見']:
                    json_dict['読影所見'][line_id]["raw_text"] = '\n'.join(line_cache)

                ''' writing new_ann to json'''
                for key in sorted(cid2tag.keys(), key=lambda x: int(x[1:]), reverse=True):
                    cid = int(key[1:])
                    tid, tag_type = cid2tag[key]
                    if key.startswith('e'):
                        char_list.insert(cid, '</%s>' % (name2tag[tag_type]))
                    elif key.startswith('b'):
                        elems = [name2tag[tag_type]]
                        elems.append('tid="%s"' % tid)
                        if tid in tid2cert:
                            elems.append('certainty="%s"' % tid2cert[tid])
                        char_list.insert(cid, '<%s>' % (' '.join(elems)))

                txt_line = ''.join(char_list)

                line_id, patient_id = None, None
                line_cache = []
                for line in txt_line.split('\n'):
                    z = re.match(r"## line id: (\w+) \|\|\| 匿名ID: (\w+)", line)
                    if z:
                        if line_id in json_dict['読影所見']:
                            if "所見" in json_dict['読影所見'][line_id]:
                                json_dict['読影所見'][line_id]["所見"] = '\n'.join(line_cache)
                            elif "findings" in json_dict['読影所見'][line_id]:
                                json_dict['読影所見'][line_id]["findings"] = '\n'.join(line_cache)
                        line_id, patient_id = z.groups()
                        line_cache = []
                    else:
                        line_cache.append(line)
                if line_id in json_dict['読影所見']:
                    if "所見" in json_dict['読影所見'][line_id]:
                        json_dict['読影所見'][line_id]["所見"] = '\n'.join(line_cache)
                    elif "findings" in json_dict['読影所見'][line_id]:
                        json_dict['読影所見'][line_id]["findings"] = '\n'.join(line_cache)

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
                    help="convert_mode, i.e. x2j, j2b and b2j", metavar="CONVERT_MODE")
parser.add_argument("--xls", dest="xls_file",
                    help="input excel file", metavar="INPUT_FILE")
parser.add_argument("--json", dest="json_file",
                    help="output excel file", metavar="OUTPUT_FILE")
parser.add_argument("--brat", dest="brat_file",
                    help="output brat txt and ann files", metavar="ANNOTATION_FILE")
parser.add_argument("--bio", dest="bio_file",
                    help="input bio file", metavar="BIO_FILE")
parser.add_argument("--xml", dest="xml_file",
                    help="output xml file", metavar="XML_FILE")
parser.add_argument("--njson", dest="new_json",
                    help="output new json", metavar="OUTPUT_FILE")

args = parser.parse_args()

if args.mode in 'xls2json':
    json_dict = read_xls(args.xls_file)
    dump_json(json_dict, args.json_file)
elif args.mode == 'json2brat':
    extract_brat_from_json(args.json_file, args.brat_file)
elif args.mode == 'brat2json':
    combine_brat_to_json(args.json_file, args.brat_file, args.new_json)
elif args.mode == 'bio2xml':
    convert_bio_to_xml(args.bio_file, args.xml_file)


