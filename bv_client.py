import subprocess
import requests
import json
import os
import csv
import re
import pandas
from terminaltables import AsciiTable
import datetime
import platform
import socket

class BV_Client(object):

    API_KEY = "API_KEY"
    API_SERVER_URL = "http://10.159.137.189/"
    # API_SERVER_URL = "http://192.168.31.190/"
    TOKEN_SERVER_URL = "http://10.159.137.189:9898/token"
    # TOKEN_SERVER_URL = "http://192.168.31.190:9898/token"
    csv_emotion_path = 'inc\\combined.csv'
    # csv_emotion_path = 'inc/combined.csv'
    converted_audio_path = 'tmp\\tmp_audio.wav'
    # converted_audio_path = 'tmp/tmp_audio.wav'

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
            command = 'lib\\bin\\ffmpeg.exe -i {} -ac 1 -c:a pcm_s16le -ar 8000 -loglevel panic {}' \
                if platform.system() == 'Windows' else 'ffmpeg -i {} -ac 1 -c:a pcm_s16le -ar 8000 -loglevel panic {}'
            convert_query = command.format(
                audio_path, BV_Client.converted_audio_path
            )
            print("   >>>converting to WAV PCM 8 KHz, 16-bit Mono ")
            subprocess.call(convert_query, shell=True)
            # os.system(convert_query)
            print("   >>>converting is done ")
        except Exception as e:
            raise Exception("format error: \r\n" + str(e))

    def get_bv_analysis(self, result=False):
        '''
        :param result:
        :return:
        '''
        print("   >>>waiting for server result")
        res = requests.post(BV_Client.TOKEN_SERVER_URL,
                            data={"grant_type": "client_credentials", "apiKey": BV_Client.API_KEY})
        token = res.json()['access_token']
        headers = {"Authorization": "Bearer " + token}
        pp = requests.post(BV_Client.API_SERVER_URL + "v5/recording/start", json={"dataFormat": {"type": "WAV"}},
                           verify=False,
                           headers=headers)
        if pp.status_code != 200:
            raise Exception('unsuccessful connection: \r\n {} \r\n {}'.format(pp.status_code, pp.content))
        recording_id = pp.json()['recordingId']
        with open(BV_Client.converted_audio_path, 'rb') as wavdata:
            r = requests.post(BV_Client.API_SERVER_URL + "v5/recording/" + recording_id, data=wavdata, verify=False,
                              headers=headers)
        self.bv_result = r.json()['result']['analysisSegments']

        # with open('test.log', 'a') as f:
        #     f.write(str(r.json()))
        #     f.write('\r\n')

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
                    key = re.sub(r'(?:_zoom_c555l|_smart_lav).*\.mp3$', '', item[0])
                    value = re.sub(r'[0-9]+', '', item[1])
                    emotion_dict.update([(key, value)])
        return emotion_dict

    def get_mapping_evaluation(self, is_segmented = False, **segment_info):
        '''

        :param is_segmented:
        :param segment_info:
        :return:
        '''
        print('   >>>Beyond Verbal Result received, Working on Evaluation')
        matrix_result_dict = {
            'Neutral': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0, 'Sadness/Uncertainty/Boredom': 0,
                        'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0},
            'Happiness/Enthusiasm/Friendliness': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0,
                                                  'Sadness/Uncertainty/Boredom': 0,
                                                  'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0,
                                                  'Inexplicit emotion': 0},
            'Sadness/Uncertainty/Boredom': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0,
                                            'Sadness/Uncertainty/Boredom': 0,
                                            'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0},
            'Warmth/Calmness': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0, 'Sadness/Uncertainty/Boredom': 0,
                                'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0},
            'Anger/Dislike/Stress': {'Neutral': 0, 'Happiness/Enthusiasm/Friendliness': 0,
                                     'Sadness/Uncertainty/Boredom': 0,
                                     'Warmth/Calmness': 0, 'Anger/Dislike/Stress': 0, 'Inexplicit emotion': 0}
        }
        participant_id = self.study_log['participantID']
        test_start_time = pandas.to_datetime(self.study_log['recordings'][0]['start'], unit='ms')
        study_audio_segments = self.study_log['prompts']

        init_start_time = 0
        init_end_time = 0
        if is_segmented:
            init_offset_index = segment_info.get('init_offset_index')
            init_start_time = segment_info.get('init_start_time')
            init_end_time = segment_info.get('init_end_time')
            study_audio_segments = study_audio_segments[init_offset_index:]

        for index, segment in enumerate(study_audio_segments):
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

            # print("compare {} and {}".format(segment_start_offset, init_end_time))
            print('is Segment: {}'.format(is_segmented))
            print((segment_start_offset, init_end_time))
            print('length: {}'.format(len(study_audio_segments)))
            print((index, len(study_audio_segments)-1))

            if (is_segmented and (segment_start_offset >= init_end_time)) \
                    or \
                    (is_segmented and (index == len(study_audio_segments)-1)):
                result_dict = self.generate_result_table(matrix_result_dict, is_segmented=True)
                print('in block')
                return (index, result_dict['part_data'], result_dict['part_table'])

            bv_label = self.get_single_bv_segment_result(segment_start_offset, segment_end_offset, init_start_time)
            matrix_result_dict[expected_emotion][bv_label] = matrix_result_dict[expected_emotion][bv_label] + 1
        print('   >>>Generating result table')
        self.generate_result_table(matrix_result_dict)

    def generate_result_table(self, matrix_result_dict, is_segmented=False, extern_writer=False):
        '''
        :param matrix_result_dict:
        :return:
        '''
        neutral_result = matrix_result_dict['Neutral'] if not extern_writer else matrix_result_dict['neutral_result']
        happy_result = matrix_result_dict['Happiness/Enthusiasm/Friendliness'] if not extern_writer else matrix_result_dict['happy_result']
        frustration_result = matrix_result_dict['Sadness/Uncertainty/Boredom'] if not extern_writer else matrix_result_dict['frustration_result']
        relaxed_result = matrix_result_dict['Warmth/Calmness'] if not extern_writer else matrix_result_dict['relaxed_result']
        angry_result = matrix_result_dict['Anger/Dislike/Stress'] if not extern_writer else matrix_result_dict['angry_result']

        # miss_result = matrix_result_dict['Inexplicit emotion']
        neutral_correct_rate = self.get_correct_rate('Neutral', neutral_result)
        happy_correct_rate = self.get_correct_rate('Happiness/Enthusiasm/Friendliness', happy_result)
        frustration_correct_rate = self.get_correct_rate('Sadness/Uncertainty/Boredom', frustration_result)
        relaxed_correct_rate = self.get_correct_rate('Warmth/Calmness', relaxed_result)
        angry_correct_rate = self.get_correct_rate('Anger/Dislike/Stress', angry_result)
        sum_correct_rate = round((neutral_correct_rate[1] + happy_correct_rate[1] + frustration_correct_rate[1] +
                                  relaxed_correct_rate[1] + angry_correct_rate[1]) / 5, 2)

        table_data = [
            ['BMW\\BV', 'neutral', 'happy / surprised', 'frustration / confused / bored', 'relaxed', 'angry',
             'Not recognized', 'correct rate'],
            ['neutral', neutral_result['Neutral'], neutral_result['Happiness/Enthusiasm/Friendliness'],
             neutral_result['Sadness/Uncertainty/Boredom'], neutral_result['Warmth/Calmness'],
             neutral_result['Anger/Dislike/Stress'],
             neutral_result['Inexplicit emotion'], neutral_correct_rate[0]],

            ['happy / surprised', happy_result['Neutral'], happy_result['Happiness/Enthusiasm/Friendliness'],
             happy_result['Sadness/Uncertainty/Boredom'], happy_result['Warmth/Calmness'],
             happy_result['Anger/Dislike/Stress'], happy_result['Inexplicit emotion'], happy_correct_rate[0]],

            ['frustration / confused / bored', frustration_result['Neutral'],
             frustration_result['Happiness/Enthusiasm/Friendliness'],
             frustration_result['Sadness/Uncertainty/Boredom'], frustration_result['Warmth/Calmness'],
             frustration_result['Anger/Dislike/Stress'], frustration_result['Inexplicit emotion'],
             frustration_correct_rate[0]],

            ['relaxed', relaxed_result['Neutral'], relaxed_result['Happiness/Enthusiasm/Friendliness'],
             relaxed_result['Sadness/Uncertainty/Boredom'], relaxed_result['Warmth/Calmness'],
             relaxed_result['Anger/Dislike/Stress'], relaxed_result['Inexplicit emotion'], relaxed_correct_rate[0]],

            ['angry', angry_result['Neutral'], angry_result['Happiness/Enthusiasm/Friendliness'],
             angry_result['Sadness/Uncertainty/Boredom'], angry_result['Warmth/Calmness'],
             angry_result['Anger/Dislike/Stress'], angry_result['Inexplicit emotion'], angry_correct_rate[0]],

            ['---', '---', '---', '---', '---', '---', '---', '>>>sum correct rate: {}%<<<'.format(sum_correct_rate)]
        ]
        table = AsciiTable(table_data)

        if is_segmented:
            return {
                'part_table': table.table,
                'part_data': {
                    'neutral_result': neutral_result,
                    'happy_result': happy_result,
                    'frustration_result': frustration_result,
                    'relaxed_result': relaxed_result,
                    'angry_result': angry_result
                    }
                }

        print(table.table)
        if extern_writer:
            return table.table
        return self.write_result(table.table)

    def write_result(self, table):
        '''
        :param table:
        :return:
        '''
        created_in = datetime.datetime.now()
        f = open('result/{}.txt'.format(self.audio_name), 'w+')
        f.write('--- result for {} generated in {} ---\r\n'.format(self.audio_name, created_in))
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
            return ('labeled: {} | recognized: {} | -> {}%'.format(denominator, fraction, 0), 0)
        return (
        'labeled: {} | recognized: {} -> | {}%'.format(denominator, fraction, round((fraction / denominator) * 100, 2))
        , round((fraction / denominator) * 100, 2))

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

    def get_single_bv_segment_result(self, segment_start_offset, segment_end_offset, init_start_time):
        '''

        :param segment_start_offset:
        :param segment_end_offset:
        :param init_start_time:
        :return:
        '''
        current_max_sore = 0
        current_label = 'Inexplicit emotion'
        for segment in self.bv_result:
            offset = segment['offset'] + init_start_time
            end = segment['end'] + init_start_time
            if segment_start_offset >= offset and segment_end_offset <= end:
                label = segment['analysis']['Emotion_group']['Group']
                # if label == 'Inexplicit emotion': continue
                sore = int(float(segment['analysis']['Emotion_group']['Score']))
                if sore > current_max_sore:
                    current_max_sore = sore
                    current_label = label
                else:
                    continue
        return current_label

def audio_length_validate(audio_path, just_len=False):
    '''

    :param audio_path:
    :param just_len:
    :return:
    '''
    command = 'lib\\bin\\ffprobe.exe -show_entries format=duration -sexagesimal -loglevel panic -i {}' \
        if platform.system() == "Windows" else 'ffprobe -show_entries format=duration -sexagesimal -loglevel panic -i {}'
    command_query = command.format(audio_path)
    raw_duration = subprocess.check_output(command_query, shell=True)
    modi_raw_duration = re.sub(r'([\[/?FORMAT\]]+)|(duration=)','',raw_duration.decode()).replace('\r','').replace('\n', '')
    hour = 0 if not re.search(r'^[0-9]+', modi_raw_duration) else int(re.search(r'^[0-9]+', modi_raw_duration).group())
    minu = int(re.sub(r'(^[0-9]*:)|(:[.0-9]*$)', '', modi_raw_duration))
    sec = float(re.search(r'[.0-9]*$', modi_raw_duration).group())
    length_in_sec = (hour * 60 * 60) + minu * 60 + sec
    if just_len:
        return length_in_sec * 1000
    limit_in_sec = 33 * 60
    if length_in_sec < limit_in_sec:
        return True
    return False



if __name__ == '__main__':

    audio_files = os.listdir(os.path.abspath('audio'))
    for audio in audio_files:
        audio_path = os.path.abspath('audio\\'+audio) if platform.system() == 'Windows' else os.path.abspath('audio/'+audio)
        # audio_path = os.path.abspath('audio/' + audio)
        print('\r\n>>>!!!Working on audio >>>\'{}\'<<<!!!'.format(audio))
        participant_id = re.sub(r'_[0-9].m4a$', '', audio)
        study_log_path = os.path.abspath('study_logs/' + participant_id + '.json')
        if audio_length_validate(audio_path):
            bv_client = BV_Client(audio, audio_path, study_log_path).get_bv_analysis()
            bv_client.get_mapping_evaluation()
        else:
            print('   >>>{} is being split into 20 min. long segments'.format(audio))
            command = 'lib\\bin\\ffmpeg.exe -i {} -c copy -map 0 -loglevel panic -segment_time 1200 -f segment tmp\\segments_tmp\\{}_part_%03d.m4a' \
                if platform.system() == 'Windows' else 'ffmpeg -i {} -c copy -map 0 -loglevel panic -segment_time 1200 -f segment tmp/segments_tmp/{}_%01d.m4a'
            command_query = command.format(audio_path, participant_id)
            raw_duration = subprocess.check_output(command_query, shell=True)
            segmented_audio_files = os.listdir(os.path.abspath('tmp\\segments_tmp')) \
                if platform.system() == 'Windows' else os.listdir(os.path.abspath('tmp/segments_tmp'))

            init_offset_index = 0
            init_start_time = 0
            init_end_time = 0

            target_result_path = 'result\\{}.txt'.format(audio) if platform.system() == 'Windows' else 'result/{}.txt'.format(audio)
            if os.path.isfile(target_result_path):
                os.remove(target_result_path)
            f = open(target_result_path, 'a+')
            created_in = datetime.datetime.now()
            f.write('--- result for {} generated in {} ---\r\n'.format(audio, created_in))


            incremented_table_data = None
            last_loop_index = len(segmented_audio_files) - 1
            for index, segmented_audio in enumerate(segmented_audio_files):
                segmented_audio_path = os.path.abspath('tmp\\segments_tmp\\' + segmented_audio) if platform.system() == 'Windows' else os.path.abspath(
                    'tmp/segments_tmp/' + segmented_audio)

                init_end_time = init_end_time + audio_length_validate(segmented_audio_path, just_len=True)
                print('   >>>!!!working on segment {} ({} to {} Min.)of {}!!!'.
                      format(segmented_audio, round(init_start_time/1000/60, 2), round(init_end_time/1000/60, 2), audio))
                f.write('\r\n   >>>!!!Result for segment {} ({} to {} Min.)of {}!!!\r\n'
                        .format(segmented_audio, round(init_start_time/1000/60, 2), round(init_end_time/1000/60, 2), audio))
                bv_client = BV_Client(segmented_audio, segmented_audio_path, study_log_path).get_bv_analysis()
                incremented_index, part_data, part_table = bv_client.get_mapping_evaluation(is_segmented=True, init_offset_index=init_offset_index,
                                                               init_start_time=init_start_time, init_end_time=init_end_time)
                f.write(part_table)
                print(part_table)
                if incremented_index:
                    init_offset_index = init_offset_index + incremented_index

                if not incremented_table_data:
                    incremented_table_data = part_data
                else:
                    for label, results in part_data.items():
                        for emotion, value in incremented_table_data[label].items():
                            prev_value = incremented_table_data[label][emotion]
                            incremented_value = part_data[label][emotion]
                            incremented_table_data[label][emotion] = prev_value + incremented_value

                init_start_time = init_end_time
                os.remove(segmented_audio_path)

                if last_loop_index == index:
                    print('   >>> Combined Result for {} <<<'.format(audio))
                    combined_table = bv_client.generate_result_table(incremented_table_data, extern_writer=True)
                    f.write('\r\n   >>>!!!Combined Result for {}!!!\r\n'.format(audio))
                    f.write(combined_table)
                    f.close()
