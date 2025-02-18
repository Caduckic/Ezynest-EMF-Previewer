import tkinter as tk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
import tempfile
import subprocess
from lxml import etree
import base64
import cairosvg
import os
import io

def extract_emf_from_xml(xml_path):
    emf_data_list = []
    try:
        parser = etree.XMLParser(strip_cdata=False)
        tree = etree.parse(xml_path, parser=etree.XMLParser(strip_cdata=False))
        root = tree.getroot()
        image_elems = root.findall(".//Image")

        for image_elem in image_elems:
            raw_xml = etree.tostring(image_elem, encoding="unicode")

            cdata_start = raw_xml.find("<![CDATA[") + 9
            cdata_end = raw_xml.find("]]>")

            if cdata_start != -1 and cdata_end != -1:
                emf_data = raw_xml[cdata_start:cdata_end].strip()
                emf_data_list.append(base64.b64decode(emf_data))
    except Exception as e:
        print(f"Failed to parse XML: {e}")
        return None
    
    return emf_data_list

def convert_emf_to_image(emf_datas):
    global images
    images = []
    try:
        for emf_data in emf_datas:
            with tempfile.NamedTemporaryFile(suffix=".emf", delete=False) as temp_emf:
                emf_path = temp_emf.name
                temp_emf.write(emf_data)

            process = subprocess.run(
                ["unoconv", "--format", "svg", emf_path],
                capture_output=True
            )

            if process.returncode == 0:
                svg_path = emf_path.replace(".emf", ".svg")
                modify_svg_bg_color(svg_path)
                with open(svg_path, "rb") as f:
                    svg_data = f.read()

                png_data = cairosvg.svg2png(bytestring=svg_data, scale=2)
                image = Image.open(io.BytesIO(png_data))

                os.remove(emf_path)
                os.remove(svg_path)

                width, height = image.size
                cropped_image = image.crop((0, 340, width, height - 340))
                # upscaled_image = upscale_image(cropped_image, scale_factor=2)
                images.append(cropped_image)
            else:
                print(f"unoconv failed: {process.stderr.decode()}")
                return None
    
    except Exception as e:
        print(f"EMF converstion failed: {e}")
        return None
    
    return images

def modify_svg_bg_color(svg_path, new_color="rgb(255,255,255)"):
    parser = etree.XMLParser(remove_blank_text=True)

    tree = etree.parse(svg_path, parser)
    root = tree.getroot()

    namespace = root.tag.split("}")[0].strip("{") if "}" in root.tag else None
    nsmap = {"svg": namespace} if namespace else {}

    paths = root.xpath(".//svg:path", namespaces=nsmap) if namespace else root.xpath(".//path")
    
    if not paths:
        print("No <tspan> elements found! Check the namespace or structure.")
    else:
        for path in paths:
            path.set("fill", new_color)
    
    text_elements = root.xpath(".//svg:text", namespaces=nsmap) if namespace else root.xpath(".//text")

    if not text_elements:
        print("No <text> elements found.")
        return

    # print(f"Moving {len(text_elements)} <text> elements to the front...")

    for text in text_elements:
        root.append(text)

    tree.write(svg_path, xml_declaration=True, encoding="utf-8")

def on_drop(event):
    global image_index
    image_index = 0

    file_path = event.data.strip().replace("{", "").replace("}", "")
    if file_path.lower().endswith(".xml"):
        emf_data = extract_emf_from_xml(file_path)
        if emf_data:
            images = convert_emf_to_image(emf_data)
            if images:
                # page_text.set(f"Sheet {image_index + 1} of {len(images)}")
                display_image(images[image_index])

def upscale_image(image, scale_factor=2):
    new_size = (image.width * scale_factor, image.height * scale_factor)
    return image.resize(new_size, Image.LANCZOS)

def display_image(image):
    global img, img_tk

    img = image
    resize_image()

def resize_image(event=None):
    global img, img_tk

    if img:
        window_width = root.winfo_width()
        window_height = root.winfo_height()

        img_resized = img.copy()
        img_resized.thumbnail((window_width, window_height), Image.LANCZOS)

        img_tk = ImageTk.PhotoImage(img_resized)
        label.config(image=img_tk)

def next_image():
    global images
    global image_index

    image_index += 1
    if image_index == len(images):
        image_index = 0

    page_text.set(f"Sheet {image_index + 1} of {len(images)}")

    display_image(images[image_index])

def previous_image():
    global images
    global image_index

    image_index -= 1
    if image_index < 0:
        image_index = len(images) - 1
    
    page_text.set(f"Sheet {image_index + 1} of {len(images)}")
    
    display_image(images[image_index])

root = TkinterDnD.Tk()
root.title("Ezy-EMF Viewer")
root.geometry("500x500")

label = tk.Label(root, text="Drag & Drop an XML File Here", font=("Arial", 14))
label.pack(fill="both", expand=True)

previous_button = tk.Button(root, text="previous", command=previous_image)
previous_button.place(x=10, y=10)

next_button = tk.Button(root, text="next", command=next_image)
next_button.place(x=100, y=10)

page_text = tk.StringVar(root, "Sheet 0 of 0")

page_label = tk.Label(root, textvariable=page_text, font=("Arial", 18))
page_label.place(x=10, y=50)

root.drop_target_register(DND_FILES)
root.dnd_bind("<<Drop>>", on_drop)

root.bind("<Configure>", resize_image)

root.mainloop()

