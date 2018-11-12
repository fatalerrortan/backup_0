import subprocess
import requests
import json
import os
import csv
import re
import pandas
from terminaltables import AsciiTable
import datetime

class BV_Client(object):

    API_KEY = "API_KEY"
    # API_SERVER_URL = "http://10.159.137.167/"
    API_SERVER_URL = "http://192.168.31.190/"
    # TOKEN_SERVER_URL = "http://10.159.137.167:9898/token"
    TOKEN_SERVER_URL = "http://192.168.31.190:9898/token"
    # csv_emotion_path = 'inc\\combined.csv'
    csv_emotion_path = 'inc/combined.csv'
    # converted_audio_path = 'tmp\\tmp_audio.wav'
    converted_audio_path = 'tmp/tmp_audio.wav'

    def __init__(self, audio_name, audio_path, study_log_path):
        '''

        :param audio_path:
        :param study_log_path:
        '''
        self.audio_name = audio_name
        self.bv_result = {}
        self.study_log = self.get_study_log(study_log_path)
        self.emotion_dict = self.get_emotion_csv_dict(BV_Client.csv_emotion_path, self.study_log['participantID'])
        self.audio_formatter(audio_path)

    @classmethod
    def audio_formatter(cls, audio_path):
        '''

        :param audio_path:
        :return:
        '''
        if os.path.isfile(BV_Client.converted_audio_path):
            os.remove(BV_Client.converted_audio_path)
        try:
            convert_query = 'ffmpeg -i {} -ac 1 -c:a pcm_s16le -ar 8000 -loglevel panic {}'.format(
                audio_path, BV_Client.converted_audio_path
            )
            print(">>>converting to WAV PCM 8 KHz, 16-bit Mono ")
            subprocess.call(convert_query, shell=True)
            # os.system(convert_query)
            print(">>>converting is done ")
        except Exception as e:
            raise Exception("format error: \r\n"+str(e))

    def get_bv_analysis(self, result=False):
        '''

        :param result:
        :return:
        '''
        print(">>>waiting for server result")
        res = requests.post(BV_Client.TOKEN_SERVER_URL,
                            data={"grant_type": "client_credentials", "apiKey": BV_Client.API_KEY})
        token = res.json()['access_token']
        headers = {"Authorization": "Bearer " + token}
        pp = requests.post(BV_Client.API_SERVER_URL+"v5/recording/start", json={"dataFormat": {"type": "WAV"}},
                           verify=False,
                           headers=headers)
        if pp.status_code != 200:
            raise Exception('unsuccessful connection: \r\n {} \r\n {}'.format(pp.status_code, pp.content))
        recording_id = pp.json()['recordingId']
        with open(BV_Client.converted_audio_path, 'rb') as wavdata:
            r = requests.post(BV_Client.API_SERVER_URL+"v5/recording/" + recording_id, data=wavdata, verify=False,
                              headers=headers)
        self.bv_result = r.json()['result']['analysisSegments']
        if result:
            return r.json()
        else:
            return self

    @staticmethod
    def get_study_log(study_log_path):
        with open(study_log_path) as f:
            study_log_json = json.load(f)
        return study_log_json

    @staticmethod
    def get_emotion_csv_dict(emotion_csv_path, participant_id):
        '''

        :param emotion_csv_path:
        :param participant_id:
        :return:
        '''
        emotion_dict = {}
        with open(emotion_csv_path, newline='') as emotion_csv:
            items = csv.reader(emotion_csv, delimiter=',')
            for item in items:
                if str(item[0]).startswith(participant_id):
                    key = re.sub(r'(?:_zoom_c555l|_smart_lav).*\.mp3$','',item[0])
                    value = re.sub(r'[0-9]+','',item[1])
                    emotion_dict.update([(key, value)])
        return emotion_dict

    def get_mapping_evaluation(self):
        '''

        :return:
        '''
        print('>>>Beyond Verbal Result received, Working on Evaluation')
        matrix_result_dict = {
            'Neutral': {'Neutral':0, 'Happiness/Enthusiasm/Friendliness':0, 'Sadness/Uncertainty/Boredom':0,
                        'Warmth/Calmness':0, 'Anger/Dislike/Stress':0, 'Inexplicit emotion': 0},
            'Happiness/Enthusiasm/Friendliness': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0, 'Sadness/Uncertainty/Boredom': 0,
                        'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0},
            'Sadness/Uncertainty/Boredom': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0, 'Sadness/Uncertainty/Boredom': 0,
                        'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0},
            'Warmth/Calmness': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0, 'Sadness/Uncertainty/Boredom': 0,
                        'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0},
            'Anger/Dislike/Stress': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0, 'Sadness/Uncertainty/Boredom': 0,
                        'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0}
        }

        participant_id = self.study_log['participantID']
        test_start_time = pandas.to_datetime(self.study_log['recordings'][0]['start'], unit='ms')
        study_audio_segments = self.study_log['prompts']

        for segment in study_audio_segments:
            prompt_id = participant_id + '_' + segment['promptID']
            expected_emotion = self.emotion_dict.get(prompt_id, None)
            if not expected_emotion:
                continue
            else:
                expected_emotion = self.get_mapping_and_counting(expected_emotion)
            segment_start_time = pandas.to_datetime(segment['start'], unit='ms')
            segment_start_offset = int((segment_start_time - test_start_time).seconds) * 1000
            segment_end_time = pandas.to_datetime(segment['end'], unit='ms')
            segment_end_offset = int((segment_end_time - test_start_time).seconds) * 1000
            bv_label = self.get_single_bv_segment_result(segment_start_offset, segment_end_offset)
            matrix_result_dict[expected_emotion][bv_label] = matrix_result_dict[expected_emotion][bv_label] + 1
        print('>>>Generating result table')
        return self.generate_result_table(matrix_result_dict)

    def generate_result_table(self, matrix_result_dict):
        '''

        :param matrix_result_dict:
        :return:
        '''
        neutral_result = matrix_result_dict['Neutral']
        happy_result = matrix_result_dict['Happiness/Enthusiasm/Friendliness']
        frustration_result = matrix_result_dict['Sadness/Uncertainty/Boredom']
        relaxed_result = matrix_result_dict['Warmth/Calmness']
        angry_result = matrix_result_dict['Anger/Dislike/Stress']
        # miss_result = matrix_result_dict['Inexplicit emotion']
        neutral_correct_rate = self.get_correct_rate('Neutral', neutral_result)
        happy_correct_rate = self.get_correct_rate('Happiness/Enthusiasm/Friendliness', happy_result)
        frustration_correct_rate = self.get_correct_rate('Sadness/Uncertainty/Boredom', frustration_result)
        relaxed_correct_rate = self.get_correct_rate('Warmth/Calmness', relaxed_result)
        angry_correct_rate = self.get_correct_rate('Anger/Dislike/Stress', angry_result)
        sum_correct_rate = round((neutral_correct_rate[1] + happy_correct_rate[1] + frustration_correct_rate[1] + relaxed_correct_rate[1] + angry_correct_rate[1]) / 5, 4)

        table_data = [
            ['BMW\\BV', 'neutral', 'happy / surprised', 'frustration / confused / bored', 'relaxed', 'angry', 'Not recognized', 'correct rate'],
            ['neutral', neutral_result['Neutral'], neutral_result['Happiness/Enthusiasm/Friendliness'],
             neutral_result['Sadness/Uncertainty/Boredom'], neutral_result['Warmth/Calmness'], neutral_result['Anger/Dislike/Stress'],
             neutral_result['Inexplicit emotion'], neutral_correct_rate[0]],

            ['happy / surprised', happy_result['Neutral'], happy_result['Happiness/Enthusiasm/Friendliness'],
             happy_result['Sadness/Uncertainty/Boredom'], happy_result['Warmth/Calmness'],
             happy_result['Anger/Dislike/Stress'], happy_result['Inexplicit emotion'], happy_correct_rate[0]],

            ['frustration / confused / bored', frustration_result['Neutral'], frustration_result['Happiness/Enthusiasm/Friendliness'],
             frustration_result['Sadness/Uncertainty/Boredom'], frustration_result['Warmth/Calmness'],
             frustration_result['Anger/Dislike/Stress'], frustration_result['Inexplicit emotion'], frustration_correct_rate[0]],

            ['relaxed', relaxed_result['Neutral'], relaxed_result['Happiness/Enthusiasm/Friendliness'],
             relaxed_result['Sadness/Uncertainty/Boredom'], relaxed_result['Warmth/Calmness'],
             relaxed_result['Anger/Dislike/Stress'], relaxed_result['Inexplicit emotion'], relaxed_correct_rate[0]],

            ['angry', angry_result['Neutral'], angry_result['Happiness/Enthusiasm/Friendliness'],
             angry_result['Sadness/Uncertainty/Boredom'], angry_result['Warmth/Calmness'],
             angry_result['Anger/Dislike/Stress'], angry_result['Inexplicit emotion'], angry_correct_rate[0]],

            ['---', '---', '---', '---', '---', '---', '---', '>>>sum correct rate: {}%<<<'.format(sum_correct_rate)]
        ]
        table = AsciiTable(table_data)
        print(table.table)
        return self.write_result(table.table)

    def write_result(self, table):
        '''

        :param table:
        :return:
        '''
        created_in = datetime.datetime.now()
        f = open('result/{}.txt'.format(self.audio_name), 'w+')
        f.write('--- result for {} generated in {} ---\r\n\r\n'.format(self.audio_name, created_in))
        f.write(table)

    def get_correct_rate(self, label, single_emotion_result):
        '''

        :param label:
        :param single_emotion_result:
        :return:
        '''
        fraction = single_emotion_result[label]
        denominator = sum(single_emotion_result.values())
        if denominator == 0:
            # return (fraction, 0, 0)
            return ('labeled: {} | recognized: {} -> {}%'.format(denominator, fraction, 0), 0)
        return ('labeled: {} | recognized: {} -> {}%'.format(denominator, fraction, round((fraction/denominator)*100, 4))
                , round((fraction/denominator)*100, 4))

    def get_mapping_and_counting(self, raw_expected_label):
        '''

        :param raw_expected_label:
        :return:
        '''
        mapped_label = {
            'neutral': 'Neutral',
            'happy': 'Happiness/Enthusiasm/Friendliness',
            'frustration': 'Sadness/Uncertainty/Boredom',
            'surprised': 'Happiness/Enthusiasm/Friendliness',
            'bored': 'Sadness/Uncertainty/Boredom',
            'confused': 'Sadness/Uncertainty/Boredom',
            'relaxed': 'Warmth/Calmness',
            'angry': 'Anger/Dislike/Stress'
        }.get(raw_expected_label, None)
        if mapped_label:
            return mapped_label
        else:
            raise Exception("no mapping available")

    def get_single_bv_segment_result(self, segment_start_offset, segment_end_offset):
        '''

        :param segment_start_offset:
        :param segment_end_offset:
        :return:
        '''
        current_max_sore = 0
        current_label = 'Inexplicit emotion'
        for segment in self.bv_result:
            offset = segment['offset']
            end = segment['end']
            if segment_start_offset >= offset and segment_end_offset <= end:
                label = segment['analysis']['Emotion_group']['Group']
                # if label == 'Inexplicit emotion': continue
                sore = int(float(segment['analysis']['Emotion_group']['Score']))
                if sore > current_max_sore:
                    current_max_sore = sore
                    current_label = label
                else: continue
        return current_label

if __name__ == '__main__':

    audio_files = os.listdir(os.path.abspath('audio'))
    for audio in audio_files:
        # audio_path = os.path.abspath('audio\\'+audio)
        audio_path = os.path.abspath('audio/'+audio)
        print('\r\n>>>!!!Working on audio >>>\'{}\'<<<!!!'.format(audio))
        participant_id = re.sub(r'_(?:0|1).m4a$', '', audio)
        study_log_path = os.path.abspath('study_logs/' + participant_id + '.json')
        bv_client = BV_Client(audio, audio_path, study_log_path).get_bv_analysis()
        bv_client.get_mapping_evaluation()




