import os
from argparse import ArgumentParser
from transformers import BertTokenizer, BertModel


def extend_bert_vocab(text_file, PRE_BERT, MODEL_URL):
    # PRE_BERT='/Users/fei-c/Resources/embed/L-12_H-768_A-12_E-30_BPE'
    # MODEL_URL='./checkpoints/'
    tokenizer = BertTokenizer.from_pretrained(PRE_BERT, do_lower_case=False, do_basic_tokenize=False)
    model = BertModel.from_pretrained(PRE_BERT)

    unk_toks = []
    with open(text_file, 'r') as fi:
        for line in fi:
            toks = line.strip().split()
            tokenized = tokenizer.tokenize(line.strip())

            deunk = []
            for i in range(len(tokenized)):
                tok = tokenized.pop(0)
                if tok.startswith('##'):
                    deunk[-1] += tok[2:]
                else:
                    deunk.append(tok)
            assert len(deunk) == len(toks)
            for d, t in zip(deunk, toks):
                if d == '[UNK]':
                    unk_toks.append(t)
    print('number of [UNK] tokens: %i, vocab size of [UNK] tokens: %i' % (len(unk_toks), len(set(unk_toks))))

    tokenizer.add_tokens(list(set(unk_toks)))
    model.resize_token_embeddings(len(tokenizer))

    if os.path.exists(MODEL_URL):
        raise ValueError("Output directory ({}) already exists and is not empty.".format(MODEL_URL))
    if not os.path.exists(MODEL_URL):
        os.makedirs(MODEL_URL)
    model.save_pretrained(MODEL_URL)
    tokenizer.save_pretrained(MODEL_URL)


parser = ArgumentParser(description='Add new tokens into an existing bert tokenizer.')
parser.add_argument("--txt", dest="txt_file",
                    help="txt file for mlm training")
parser.add_argument("--pre", dest="pre_model",
                    help="pre_trained bert model")
parser.add_argument("--model", dest="model_url",
                    help="new model dir to save")
args = parser.parse_args()
extend_bert_vocab(args.txt_file, args.pre_model, args.model_url)
