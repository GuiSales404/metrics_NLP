# -*- coding: utf-8 -*-
"""STT-Wit.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1vYEMPk_DBSI8zoz_2lJRxFD_A63B2y-v

# Speech 2 Text

## Install and Imports
"""

!pip install SpeechRecognition google-cloud-speech

from pathlib import Path
import pandas as pd

from google.colab import drive
drive.mount('/content/drive', force_remount=True)

data_path = Path('/content/drive/MyDrive/AWS API datasets-results/mozilla')

"""# Wit API"""

!pip install pydub 
!pip install --user -U nltk

import os, pydub, requests, io, json
from pydub import AudioSegment

def split_into_chunks(segment, length=20000/1001, split_on_silence=False, noise_threshold=-36): 
    chunks = list()
    
    if split_on_silence is False:
        for i in range(0, len(segment), int(length*1000)):
            chunks.append(segment[i:i+int(length*1000)])
    else:
        while len(chunks) < 1:
            chunks = pydub.silence.split_on_silence(segment, noise_threshold)
            noise_threshold += 4

    for i, chunk in enumerate(chunks):
        if len(chunk) > int(length*1000):
            subchunks = split_into_chunks(chunk, length, split_on_silence, noise_threshold+4)
            chunks = chunks[:i-1] + subchunks + chunks[i+1:]

    return chunks

def preprocess_audio(audio):
  return audio.set_sample_width(2).set_channels(1).set_frame_rate(8000)

def read_audio_into_chunks(file_path):
    audio = AudioSegment.from_file(file_path)
    return split_into_chunks(preprocess_audio(audio))

def transcribe_audio_wit(file_path):
    url = 'https://api.wit.ai/speech'
    key = 'F2OWWM5RTU7DAF4PLKLLTSX66VJ6XQ5X'

    # defining headers for HTTP request
    headers = {
        'authorization': 'Bearer ' + key,
        'content-type': 'audio/raw;encoding=signed-integer;bits=16;rate=8000;endian=little',
    }

    chunks = read_audio_into_chunks(file_path)

    text = []
    for audio in chunks:
        response = requests.post(
            url,
            headers=headers,
            data=io.BufferedReader(io.BytesIO(audio.raw_data))
        )
        
        reply = response.content.decode("utf-8")
        reply = reply.split('\r\n')

        data = json.loads(reply[-1])
        if 'text' in data:
            text.append(data['text'])
    
    return ' '.join(text)


# Apply on single file
text = transcribe_audio_wit(data_path /'wav'/'common_voice_pt_19277034.mp3')
print(text)

# Apply on Mozilla dataset
df = pd.read_csv(f'{data_path}/metrics_generation.csv', sep=',')

for file in df.file:
    audio_source = str(data_path)+'/wav/'+file
    df.loc[df['file'] == file, 'translation'] = transcribe_audio_wit(audio_source)

df.to_csv(str(data_path)+'/transcribed_wit_api.csv', sep=',', index=False)

"""# Apply metrics to results"""

from itertools import chain
import re
from gensim import corpora
from gensim.matutils import softcossim
import nltk
nltk.download('rslp')
nltk.download('wordnet')
from nltk.translate import bleu_score, meteor_score
from datasets import load_metric
wer = load_metric("wer")


def clean_str(x):
    return re.sub('\W', ' ', x).lower()


def cosine_similarity(reference, hypothesis, model):
    reference = reference.split()
    hypotesis = hypothesis.split()
    documents = [hypotesis, reference]
    dictionary = corpora.Dictionary(documents)

    similarity_matrix = emb_models[model].similarity_matrix(dictionary)

    hypotesis = dictionary.doc2bow(hypotesis)
    reference = dictionary.doc2bow(reference)

    return softcossim(hypotesis, reference, similarity_matrix)


def bleu(reference, hypothesis):
    references = [reference.split()]
    hypothesis = hypothesis.split()

    if len(references[0]) == 1:
        weights=(1.0, 0.0, 0.0, 0.0)
    elif len(references[0]) == 2:
        weights=(0.5, 0.5, 0.0, 0.0)
    elif len(references[0]) == 3:
        weights=(0.4, 0.3, 0.3, 0.0)
    else:
        weights=(0.4, 0.3, 0.2, 0.1)

    return bleu_score.sentence_bleu(references, hypothesis, weights=weights)


pt_stemmer = nltk.stem.RSLPStemmer()
def meteor(reference, hypothesis):
    references = [reference.split()]
    # references = [word for word in references if word != '']
    hypothesis = hypothesis.split()
    return meteor_score.meteor_score(references, hypothesis, stemmer=pt_stemmer)

from gensim.models import KeyedVectors

emb_models = {
    'word2vec_cbow_s50': KeyedVectors.load_word2vec_format('JIDM/embeddings/cbow_s50.txt'),
    'word2vec_skip_s50': KeyedVectors.load_word2vec_format('JIDM/embeddings/skip_s50.txt')
}

"""### Load transcriptions"""

# Wit API
file_path = path_voxforge+'/transcribed_wit_api.tsv'
wit_api_result_df = pd.read_csv(file_path, sep='\t')
wit_api_result_df.dropna(inplace=True)
print(f'wit_api_result_df.shape: {wit_api_result_df.shape}')
print(wit_api_result_df.head())

transcribed_wit_df = wit_api_result_df

"""### Cossine Metric"""

for model in emb_models:
    print(f'Applying for {model}')
    for sentence, translation in zip(transcribed_wit_df.sentence, transcribed_wit_df.translation):
        original = sentence
        sentence = clean_str(sentence)
        translation = clean_str(translation)
        transcribed_wit_df.loc[transcribed_wit_df['sentence'] == original, f"cos_sim_{model}"] = cosine_similarity(sentence, translation, model)

for sentence, translation in zip(transcribed_wit_df.sentence, transcribed_wit_df.translation):
    original = sentence
    sentence = clean_str(sentence)
    translation = clean_str(translation)
    transcribed_wit_df.loc[transcribed_wit_df['sentence'] == original, 'bleu'] = bleu(sentence, translation)
    transcribed_wit_df.loc[transcribed_wit_df['sentence'] == original, 'meteor'] = meteor(sentence, translation)

"""### WER, BLEU e METEOR Metrics"""

sentences = transcribed_wit_df["sentence"].apply(clean_str)
translations = transcribed_wit_df["translation"].apply(clean_str)
print(f'WER: {wer.compute(predictions=translations, references=sentences)*100}')

print(f'bleu: {transcribed_wit_df["bleu"].mean()}')
print(f'meteor: {transcribed_wit_df["meteor"].mean()}')

for model in emb_models:
    print(f'{model}: {transcribed_wit_df[f"cos_sim_{model}"].mean()}')

transcribed_wit_df.to_csv(path_voxforge+'/transcribed_wit_api_metrics.tsv', sep='\t', index=False)