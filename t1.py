

import re
import sys
import time
import os

from google.cloud import speech
import pyaudio
from six.moves import queue

# Audio recording parameters
STREAMING_LIMIT = 240000  # 4 minutes
SAMPLE_RATE = 16000
CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms



os.environ["GOOGLE_APPLICATION_CREDENTIALS"]="./key.json"

def get_current_time():
    """Return Current Time in MS."""

    return int(round(time.time() * 1000))


class ResumableMicrophoneStream: #this class will generate microphone voice in real time
    """Opens a recording stream as a generator yielding the audio chunks."""

    def __init__(self, rate, chunk_size):
        self._rate = rate
        self.chunk_size = chunk_size
        self._num_channels = 1
        self._buff = queue.Queue()
        self.closed = True
        self.start_time = get_current_time()
        self.restart_counter = 0
        self.audio_input = []
        self.last_audio_input = []
        self.result_end_time = 0
        self.is_final_end_time = 0
        self.final_request_end_time = 0
        self.bridging_offset = 0
        self.last_transcript_was_final = False
        self.new_stream = True
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._num_channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

    def __enter__(self):

        self.closed = False
        return self

    def __exit__(self, type, value, traceback):

        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, *args, **kwargs):
        """Continuously collect data from the audio stream, into the buffer."""

        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        """Stream Audio from microphone to API and to local buffer"""

        while not self.closed:
            data = []

            if self.new_stream and self.last_audio_input:

                chunk_time = STREAMING_LIMIT / len(self.last_audio_input)

                if chunk_time != 0:

                    if self.bridging_offset < 0:
                        self.bridging_offset = 0

                    if self.bridging_offset > self.final_request_end_time:
                        self.bridging_offset = self.final_request_end_time

                    chunks_from_ms = round(
                        (self.final_request_end_time - self.bridging_offset)
                        / chunk_time
                    )

                    self.bridging_offset = round(
                        (len(self.last_audio_input) - chunks_from_ms) * chunk_time
                    )

                    for i in range(chunks_from_ms, len(self.last_audio_input)):
                        data.append(self.last_audio_input[i])

                self.new_stream = False

            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            self.audio_input.append(chunk)

            if chunk is None:
                return
            data.append(chunk)
            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)

                    if chunk is None:
                        return
                    data.append(chunk)
                    self.audio_input.append(chunk)

                except queue.Empty:
                    break

            yield b"".join(data)


def listen_print_loop(responses, stream): #convert voice into text print the data
    """Iterates through server responses and prints them.
    The responses passed is a generator that will block until a response
    is provided by the server.
    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
    print only the transcription for the top alternative of the top result.
    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    """

    def off():
        canvas.itemconfig(oval, fill='red')
        canvas.update_idletasks()
    for response in responses:

        if get_current_time() - stream.start_time > STREAMING_LIMIT:
            stream.start_time = get_current_time()
            break

        if not response.results:
            continue

        result = response.results[0]

        if not result.alternatives:
            continue

        transcript = result.alternatives[0].transcript

        result_seconds = 0
        result_micros = 0

        if result.result_end_time.seconds:
            result_seconds = result.result_end_time.seconds

        if result.result_end_time.microseconds:
            result_micros = result.result_end_time.microseconds

        stream.result_end_time = int((result_seconds * 1000) + (result_micros / 1000))

        corrected_time = (
            stream.result_end_time
            - stream.bridging_offset
            + (STREAMING_LIMIT * stream.restart_counter)
        )
        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.

        if result.is_final:


            translate_text.insert(END,"\033[K")
            translate_text.insert(END,str(corrected_time) + ": " + transcript + "\n")


            stream.is_final_end_time = stream.result_end_time
            stream.last_transcript_was_final = True

            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            if re.search(r"\b(exit|quit)\b", transcript, re.I):

                off()



                translate_text.insert(END,"Exiting...\n")

                translate_text.update_idletasks()


                stream.closed = True
                break

        else:

            translate_text.insert(END,"\033[K")
            translate_text.insert(END,str(corrected_time) + ": " + transcript + "\r")
            translate_text.update_idletasks()

            stream.last_transcript_was_final = False




def main(self):
    """start bidirectional streaming from microphone input to speech API"""

    def on():

        canvas.itemconfig(oval, fill='green')
        canvas.update_idletasks()

    # translate_text.configure(state=NORMAL)
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code="en-US",
        max_alternatives=1,
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config, interim_results=True
    )

    mic_manager = ResumableMicrophoneStream(SAMPLE_RATE, CHUNK_SIZE)    #real time voice

    translate_text.insert(END,'\nListening, say "Quit" or "Exit" to stop.\n\n')
    translate_text.insert(END,"End (ms)       Transcript Results/Status\n")
    translate_text.insert(END,"=====================================================\n")
    translate_text.update_idletasks()
    on()
    translate_text.update_idletasks()



    with mic_manager as stream:

        while not stream.closed:

            translate_text.insert(END,"\n\n" + str(STREAMING_LIMIT * stream.restart_counter) + ": NEW REQUEST\n")
            translate_text.update_idletasks()


            stream.audio_input = []
            audio_generator = stream.generator()

            requests = (
                speech.StreamingRecognizeRequest(audio_content=content)
                for content in audio_generator
            )

            responses = client.streaming_recognize(streaming_config, requests)

            # Now, put the transcription responses to use.
            a=listen_print_loop(responses, stream)
            translate_text.insert(END,str(a))
            translate_text.update_idletasks()
            # translate_text.configure(state=DISABLED)
            if stream.result_end_time > 0:
                stream.final_request_end_time = stream.is_final_end_time
            stream.result_end_time = 0
            stream.last_audio_input = []
            stream.last_audio_input = stream.audio_input
            stream.audio_input = []
            stream.restart_counter = stream.restart_counter + 1

            if not stream.last_transcript_was_final:

                translate_text.insert(END,"\n")
                translate_text.update_idletasks()


            stream.new_stream = True





from google.cloud import speech
import pyaudio
from six.moves import queue

import tkinter as tk
from tkinter import *







root=tk.Tk()

root.title("SPEECH TO TEXT RECOGNITION ")
root.geometry("1000x771")
root.configure(bg='white')
Input_Voice=StringVar()


Negation_Frame=LabelFrame(root,bg="white")
Negation_Frame.place(x=0,y=0,height=200,width=1000)


canvas = Canvas(Negation_Frame, height=40, width=100)
canvas.pack()
x = 50
y = 25
r = 10
x0 = x - r
y0 = y - r
x1 = x + r
y1 = y + r
oval=canvas.create_oval(x0, y0, x1, y1, fill="", outline='black')




Input_Frame=LabelFrame(root,bg="gray")
Input_Frame.place(x=0,y=50,height=200,width=1000)

rec_label=Label(master=Input_Frame,text="Recording Device",bg="gray",fg="white",relief=GROOVE,font=("times new roman",20,'bold')).place(x=8,y=10,width=250,height=30)
Push_to_talk_label = Label(master=Input_Frame, text="Push-To_Talk", bg="gray",fg="white", relief=GROOVE,font=("times new roman", 20, 'bold')).place(x=650,y=10,width=250,height=30)
download_button=Button(master=Input_Frame,text="download here!",font=("times new roman",12,'bold'),width=20, height=1, compound="c").place(x=10,y=55,width=250,height=30)

controls_button=Entry(master=Input_Frame,text="Control-A",font=("times new roman",12,'bold'),width=22).place(x=650,y=55,width=200,height=30)
set_button=Button(master=Input_Frame,text="Set",font=("times new roman",12,'bold'),width=10, height=1, compound="c")
set_button.place(x=860,y=55,width=40,height=30)

set_button.bind('k',main)


translate_Frame = Frame(root, bg="gray", relief=GROOVE)
translate_Frame.place(x=1, y=200, height=500, width=1000)

scrol_y = Scrollbar(translate_Frame, orient=VERTICAL)
translate_text = Text(translate_Frame,yscrollcommand=scrol_y.set,bg="black",fg="white",font=("times new roman",20,'bold'))
scrol_y.pack(side=RIGHT, fill=Y)
scrol_y.config(command=translate_text.yview)
translate_text.pack(fill=BOTH, expand=1)



Bottom_Frame=Frame(root,bg="gray")
Bottom_Frame.place(x=0, y=700, height=70, width=1000)
clear_button=Button(master=Bottom_Frame,text="[ Clear ]",font=("times new roman",14,'bold'),width=10, height=1, compound="c").place(x=780,y=13,width=100,height=45)
Copy_button = Button(master=Bottom_Frame, text="[ Copy ]", font=("times new roman", 14, 'bold'),width=10, height=1, compound="c").place(x=890, y=13, width=100, height=45)

root.update_idletasks()
root.mainloop()








