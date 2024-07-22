from flask import Flask, render_template, request, redirect, url_for, send_file
import google.generativeai as genai
from pathlib import Path
import assemblyai as aai
from PIL import Image
from moviepy.editor import *
from moviepy.config import change_settings
import pysrt
from gtts import gTTS
import os
import shutil
from mutagen import File
from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips, CompositeVideoClip
from moviepy.video.tools.subtitles import SubtitlesClip
import numpy as np
import re
import gc
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploaded_images/'
UPLOAD_FOLDER = 'uploaded_images'
FINAL_FOLDER = 'final_files'

if not os.path.exists(FINAL_FOLDER):
    os.makedirs(FINAL_FOLDER)

GOOGLE_API_KEY = 'AIzaSyBeuj_-fGbJA0ZaK4mKekzZWe7TXOpN_R0'
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(model_name="gemini-1.5-flash")
tmodel = genai.GenerativeModel(model_name = "models/gemini-1.0-pro")

def delete_uploaded_files():
    """Delete all files in the upload folder."""
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')

change_settings({"IMAGEMAGICK_BINARY":r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\convert.exe"})


def save_uploaded_files(uploaded_files):
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    file_paths = []
    for uploaded_file in uploaded_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], uploaded_file.filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.read())
        file_paths.append(file_path)
    return file_paths

def image_format(image_path):
    img = Path(image_path)
    if not img.exists():
        raise FileNotFoundError(f"Could not find image: {img}")
    image_parts = [
        {
            "mime_type": "image/png",
            "data": img.read_bytes()
        }
    ]
    return image_parts

def gemini_output(input_prompt, image_path):
    image_info = image_format(image_path)
    input_prompt_with_image = [input_prompt, image_info[0], ""]
    response = model.generate_content(input_prompt_with_image)
    return response.text

def sequence_text(result):
    prompt=f'''
    Basic Subtitle : 
    {result}

    - You are provided with a basic subtitle to guide a user through a website.
    - Convert it into a clear and complete content so that we can provide it as a subtitle for a tutorial video.
    - Enrich the content by changing them to be suitable for a professional tutorial video.
    - Mention the Page Number which page the content belongs to . 
    - don't Mention the navigation Items . Mention only the curerntly web .
    - It should be like same as a human explaining the content in a enriched and attractive way .
    - It should be user friendly and in an ambigious way to understand easily.
    - Check for grammar and spelling mistakes before giving the response .
    - Maintain the order of the guidence as you were provided to you.so that it will sync to the video that is playing fot this subtitle.
    '''

    res=tmodel.generate_content(prompt)
    return res.text


def retext(original_text, steps, modification):
    prompt = f"""
    Original Text:
    {original_text}
    
    Steps:
    {steps}
    
    Modification:
    {modification}
    
    Task:
    -Please modify the original text according to the steps and modifications provided.
    -Ensure the modified text follows the same steps format as the original text.
    -Include the page number where the content belongs.
    
    Modified Text:
    """
    res=tmodel.generate_content(prompt)

    return res.text


def subtitle_generater(subtitle):
    sub=pysrt.open(subtitle)

def text_generation(image_path):
    summary_prompt = (
        "Describe all the buttons and links visible in the website screenshot, including their purposes. "
        "For each button or link, specify the actions that a user can perform, such as clicking, buying, adding, viewing, filling, and visiting. "
        "Do not use examples provided. Analyze the image independently and describe all the actions/buttons present. "
        "Ensure you do not miss any actions/events or functions, as they are crucial for generating a tutorial on using the webpage."
        "Provide a comprehensive summary that accurately represents the functionality of the webpage. "
        "Do not miss any buttons, events, or actions in the screenshot."
    )
    summary_result = gemini_output(summary_prompt, image_path)

    summary_verify_prompt = (
        "Verify the summary to ensure it accurately reflects all functions and events described. "
        "Ensure actions such as clicking, buying, adding, viewing, filling, and visiting are clearly represented. "
        "Do not use examples provided. Analyze the image independently and describe all the actions/buttons present. "
        "Ensure you do not miss any actions/events or functions, as they are crucial for generating a tutorial on using the webpage."
        f"Summary:\n{summary_result}\n"
        "Do not miss any events or actions."
    )
    verify_result = gemini_output(summary_verify_prompt, image_path)

    final_response_prompt = (
        "Create a concise 2-3 line subtitle for a tutorial video on the webpage. "
        "The subtitle should guide users on performing actions such as clicking, buying, adding, viewing, filling, and visiting. "
        "Do not use examples provided. Analyze the image independently and describe all the actions/buttons present. "
        "Ensure the subtitle includes all key actions and buttons without missing any."
        f"Summary:\n{verify_result}\n"
        "The final result should contain all the available actions/buttons and their functions."
    )
    subtitle = gemini_output(final_response_prompt, image_path)
    return subtitle

def clean(text):
    pages = text.split('**Page ')

    cleaned_pages = []
    for page in pages:
        if page.strip():
            cleaned_page = page.replace('\n', ' ').strip()
            modified_string = re.sub(r'[0-9]+', '', cleaned_page).strip()
            clean_page=modified_string.replace('**','')
            clean_page=clean_page.replace('##','')
            clean=clean_page.replace(':','').strip()
            cleaned_pages.append(clean) 

    return cleaned_pages
def delete_folder(folder_path):
    """Delete all files and the folder itself."""
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)


def time_to_seconds(time_obj):
    return time_obj.hours * 3600 + time_obj.minutes * 60 + time_obj.seconds + time_obj.milliseconds / 1000

def create_subtitle_clips(subtitles, videosize, fontsize=30, font='Arial', color='white', debug=False):
    subtitle_clips = []
    for subtitle in subtitles:
        start_time = time_to_seconds(subtitle.start)
        end_time = time_to_seconds(subtitle.end)
        duration = end_time - start_time
        video_width, video_height = videosize
        text_clip = TextClip(subtitle.text, fontsize=fontsize, font=font, color=color, bg_color='black', size=(video_width * 0.5, None), method='caption').set_start(start_time).set_duration(duration)
        subtitle_x_position = 'center'
        subtitle_y_position = video_height * 9 / 10
        text_position = (subtitle_x_position, subtitle_y_position)
        subtitle_clips.append(text_clip.set_position(text_position))
    return subtitle_clips

def regenerate_sub(file_path, user):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    blocks = content.strip().split('\n\n')
    response = ''

    for block in blocks:
        match = re.match(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n(.+)', block, re.DOTALL)
        if match:
            index = match.group(1)
            timestamp = match.group(2)
            text = match.group(3).replace('\n', ' ')
            response += f"{index}\n{timestamp}\n{text}\n\n"

    prompt = f'''
    SRT File:
        {response}

        *
    Find and replace with correct spelling in all the required places. For your reference of what spellings must be changed with high priority is given below:
    {user}

    You are given with the naming conventions for a company's website and you need to replace the inappropriate words with given suitable words. 
    Don't change the Timeline of the Original SRT file.
    Check the Spelling and Return the corrected content in the same SRT format.
    Don't change any time frame details give all as it is by changing only the spelling mistakes.
    Don't mention the replaced words or other stuff only give the final replaced content.
    Don't change the time line of the original SRT file . The time frame should be same to Original SRT file and modified srt file.

    '''
    
    res = tmodel.generate_content(prompt)
    
    corrected_subtitles = res.text.strip()
    corrected_blocks = corrected_subtitles.split('\n\n')
    with open(file_path, 'w', encoding='utf-8') as corrected_file:
        for corrected_block in corrected_blocks:
            corrected_file.write(corrected_block.strip() + '\n\n')

    return file_path

def getvideofromimage(image_path, text, index):
    language = 'en'
    myobj = gTTS(text=text, lang=language, slow=False)
    output_file = "output.wav"
    myobj.save(output_file)
    audio_path=output_file
    aai.settings.api_key = "e1313b421dec4789bddac187ad824975"
    transcript = aai.Transcriber().transcribe(audio_path)
    subtitles = transcript.export_subtitles_srt()
    subtitle = f"subtitles{index}.srt"
    with open(subtitle, "w") as f:
        f.write(subtitles)
    regenerate_sub(subtitle,text)  
    audio = File(audio_path)
    duration_seconds = audio.info.length
    image = Image.open(image_path)
    image_np = np.array(image)
    image_clip = ImageClip(image_np)
    video = image_clip.set_duration(duration_seconds).set_fps(24)
    outputvideo_path = 'output_video.mp4'
    video.write_videofile(outputvideo_path, codec='libx264', fps=24)
    video_clip = VideoFileClip(outputvideo_path)
    audio_clip = AudioFileClip(audio_path)
    video_clip = video_clip.set_audio(audio_clip)
    outputvideoaudio_path = 'output_video_with_audio.mp4'
    video_clip.write_videofile(outputvideoaudio_path, codec='libx264', audio_codec='aac')
    video = VideoFileClip(outputvideoaudio_path)
    subtitles = pysrt.open(subtitle)
    output_video_file = f'final_files/output_video_with_audio_subtitling{index}.mp4'
    subtitle_clips = create_subtitle_clips(subtitles, video.size)
    final_video = CompositeVideoClip([video] + subtitle_clips)
    final_video.write_videofile(output_video_file)
    if not os.path.isfile(output_video_file):
        os.path.join(FINAL_FOLDER, output_video_file)
    os.remove(subtitle)
    os.remove(audio_path)
    os.remove(outputvideo_path)
    os.remove(outputvideoaudio_path)
    return output_video_file

def path_image_create(file_paths):
    print(file_paths)
    result = ""
    i = 1
    for file_path in file_paths:
        result += 'Page ' + str(i) + ' : ' + text_generation(file_path) + ' \n'
        i += 1
    result_text = sequence_text(result)
    result_ = clean(result_text)
    video_files = []
    index = 1
    for image, text in zip(file_paths, result_):
        video_file = getvideofromimage(image, text, index)
        video_files.append(video_file)
        index += 1
    video_clips = [VideoFileClip(video_file) for video_file in video_files]
    final_video = concatenate_videoclips(video_clips, method="compose")
    final_video_path = "static/final_output_video.mp4"
    final_video.write_videofile(final_video_path, codec='libx264', audio_codec='aac')
    if not os.path.isfile(final_video_path):
        os.path.join(FINAL_FOLDER, final_video_path)
    return result_text, final_video_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if request.method == 'POST':
        uploaded_files = request.files.getlist("files[]")
        file_paths = save_uploaded_files(uploaded_files)
        result_text, final_video_path  = path_image_create(file_paths)
        return render_template('result.html', result_text=result_text, video_path=final_video_path,file_paths=file_paths)
    
@app.route('/delete_files', methods=['POST'])
def delete_files():
    delete_uploaded_files()
    return redirect(url_for('index'))


@app.route('/process_text', methods=['POST'])
def process_text():
    if request.method == 'POST':
        textbox1 = request.form['textbox1']
        textbox2 = request.form['textbox2']
        result_text = request.form['result_text']
        video_path = request.form['video_path']
        file_paths = request.form['file_paths']
        print(file_paths)
        file_paths = file_paths.replace('[', '').replace(']', '').replace("'", "").split(',')
        file_paths = [path.strip() for path in file_paths]
        modified_result_text = retext(result_text, textbox1,textbox2)
        result_ = clean(modified_result_text)
        
        print(result_)
        video_files = []
        ind=1
        for file_path,texting in zip(file_paths,result_):
            print(file_path)
            video_file = getvideofromimage(file_path, texting, ind)
            ind+=1
            video_files.append(video_file)
        video_clips = [VideoFileClip(video_file) for video_file in video_files]
        final_video = concatenate_videoclips(video_clips, method="compose")
        final_video_path = "static/final_output_video_modified.mp4"
        final_video.write_videofile(final_video_path, codec='libx264', audio_codec='aac')
        if not os.path.isfile(final_video_path):
            os.path.join(FINAL_FOLDER, final_video_path)
        return render_template('result.html', result_text=modified_result_text, video_path=final_video_path,file_paths=file_paths)

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    try:
        app.run(debug=True)
    finally:
        delete_uploaded_files()
        delete_folder(FINAL_FOLDER)
        delete_folder(UPLOAD_FOLDER)
