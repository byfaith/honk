import numpy as np
import librosa

from scipy.cluster.vq import vq, kmeans, whiten
from .base_extractor import BaseAudioExtractor

class EditDistanceExtractor(BaseAudioExtractor):
    def __init__(self, target_audios, threshold, distortion_threshold=1, sr=16000, n_dct_filters=40, n_mels=40, f_max=4000, f_min=20, n_fft=480, hop_ms=10):
        super().__init__(target_audios, threshold)
        self.n_mels = n_mels
        self.dct_filters = librosa.filters.dct(n_dct_filters, n_mels)
        self.sr = sr
        self.f_max = f_max if f_max is not None else sr // 2
        self.f_min = f_min
        self.n_fft = n_fft
        self.hop_length = sr // 1000 * hop_ms
        self.distortion_threshold = distortion_threshold

        # Use the first audio file for now
        target = target_audios[0]
        self.processed_target = self.compute_mfccs(target)
        # TODO :: take average to make processed_target more robust


    def compute_mfccs(self, data):
        data = librosa.feature.melspectrogram(
            data,
            sr=self.sr,
            n_mels=self.n_mels,
            hop_length=self.hop_length,
            n_fft=self.n_fft,
            fmin=self.f_min,
            fmax=self.f_max)
        data[data > 0] = np.log(data[data > 0])
        data = [np.concatenate(np.matmul(self.dct_filters, x)) for x in np.split(data, data.shape[1], axis=1)]
        return np.array(data)


    def compute_edit_distance(self, data, target):
        if len(data) == 0:
            return len(target)
        if len(target) == 0:
            return len(data)
        distances = [[i for i in range(len(target) + 1)],
                     [0 for i in range(len(target) + 1)]]
        for i in range(1, len(data) + 1):
            idx = i % 2
            distances[idx][0] = i
            for j in range(1, len(target) + 1):
                temp = distances[1 - idx][j - 1] if target[j - 1] == data[i - 1] else distances[1 - idx][j - 1] + 1
                distances[idx][j] = min((distances[1 - idx][j] + 1), (distances[idx][j - 1] + 1), temp)
        return distances[len(data) % 2][-1]


    def extract_keywords(self, data, window_ms=1000, hop_ms=250):
        selected_window = []

        current_start = 0
        window_size = window_ms * (self.sr // 1000)

        mfcc_audio = self.compute_mfccs(data)
        whitened = whiten(mfcc_audio)

        k = whitened.shape[0]
        code_book, distortion = kmeans(whitened, k)

        while distortion < self.distortion_threshold:
            k -= 10
            code_book, distortion = kmeans(whitened, k)

        target_vq_window = vq(self.processed_target, code_book)[0]

        while current_start + window_size < len(data):
            window = data[current_start:current_start + window_size]

            mfcc_window = self.compute_mfccs(window)
            vq_window = vq(mfcc_window, code_book)[0]

            distance = self.compute_edit_distance(vq_window, target_vq_window)

            if distance / len(target_vq_window) < self.threshold:
                selected_window.append(current_start)

            current_start += hop_ms * (self.sr // 1000)


        return selected_window