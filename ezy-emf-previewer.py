from PIL import Image
import tempfile
import subprocess
from lxml import etree
import base64
import cairosvg
import os
import io

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.image import Image as ImageKv
from kivy.uix.button import Button
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture

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
                image = Image.open(io.BytesIO(png_data)).convert("RGBA")
                image = image.transpose(Image.FLIP_TOP_BOTTOM)

                os.remove(emf_path)
                os.remove(svg_path)

                width, height = image.size
                cropped_image = image.crop((0, 340, width, height - 340))
                upscaled_image = upscale_image(cropped_image, scale_factor=2)
                images.append(cropped_image)
            else:
                print(f"unoconv failed: {process.stderr.decode()}")
                return None
    
    except Exception as e:
        print(f"EMF converstion failed: {e}")
        return None
    
    textures = []

    for image in images:
        texture = Texture.create(size=image.size, colorfmt="rgba")
        texture.blit_buffer(image.tobytes(), colorfmt="rgba", bufferfmt="ubyte")

        textures.append(texture)

    return textures

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

def on_drop(file_path):
    file_path = file_path.decode("utf-8")
    global image_index
    image_index = 0

    if file_path.lower().endswith(".xml"):
        emf_data = extract_emf_from_xml(file_path)
        if emf_data:
            textures = convert_emf_to_image(emf_data)
            if textures:
                # page_text.set(f"Sheet {image_index + 1} of {len(images)}")
                return textures
                # return display_image(images[image_index])

def upscale_image(image, scale_factor=2):
    new_size = (image.width * scale_factor, image.height * scale_factor)
    return image.resize(new_size, Image.LANCZOS)

class DropZone(FloatLayout):
    def __init__(self, **kwargs):
        super(DropZone, self).__init__(**kwargs)
        self.image_widget = ImageKv(
            size_hint=(0.9, 1.8),
            allow_stretch=True,
            keep_ratio=True,
            pos_hint={"center_x": 0.5, "center_y": 0.5}
        )
        self.textures = []
        self.image_index = 0

        self.previous_button = Button(text="Previous Sheet", size_hint=(None, None), size=(120, 50))
        self.previous_button.bind(on_press=lambda instance: self.change_image_index(instance, 1))
        self.previous_button.pos = (20, 20)

        self.next_button = Button(text="Next Sheet", size_hint=(None, None), size=(120, 50))
        self.next_button.bind(on_press=lambda instance: self.change_image_index(instance, 1))
        self.next_button.pos = (160, 20)

        self.image_index_label = Label(text="", size_hint=(1.0, 1.0), size=(200, 50), color=(0,0,0,1), font_size=30, halign="left")
        self.image_index_label.bind(size=self.image_index_label.setter("text_size"))
        self.image_index_label.pos = (300, 20)

        self.label = Label(
            text='Drag & Drop "pics.xml" File Here',
            size_hint=(None, None),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            color=(0,0,0,1),
            font_size=30
        )

        self.add_widget(self.label)

        # self.add_widget(self.image_widget)

        with self.canvas.before:
            Color(0.8, 0.8, 0.8, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        
        self.bind(pos=self.update_bg, size=self.update_bg)

    def change_image_index(self, window, offset):
        if abs(offset) == 1:
            self.image_index += offset
            if self.image_index >= len(self.textures):
                self.image_index -= len(self.textures)
            if self.image_index < 0:
                self.image_index += len(self.textures)
            
            self.image_index_label.text = f"{self.image_index+1}/{len(self.textures)}"
            self.display_image(self.image_index)


    def update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def on_drop_file(self, window, file_path):
        self.textures = on_drop(file_path)
        if self.textures is not None:
            self.image_index = 0
            self.clear_widgets()
            self.add_widget(self.image_widget)
            self.add_widget(self.next_button)
            self.add_widget(self.previous_button)

            self.image_index_label.text = f"{self.image_index+1}/{len(self.textures)}"

            self.add_widget(self.image_index_label)
            
            self.display_image(self.image_index)
    
    def display_image(self, index):
        self.image_widget.texture = self.textures[index]
        # self.add_widget(self.image_widget)


class EzyEmfPreviewer(App):
    def build(self):
        layout = FloatLayout()
        drop_zone = DropZone()
        layout.add_widget(drop_zone)
        Window.bind(on_dropfile=drop_zone.on_drop_file)
        return layout
    
if __name__ == "__main__":
    EzyEmfPreviewer().run()