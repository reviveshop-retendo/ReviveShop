"""Parser for sce_sys/livearea/contents/template.xml, the LiveArea paper layout."""

import xml.etree.ElementTree as ET


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _findall(elem, name):
    return [c for c in elem.iter() if _local(c.tag) == name]


def _text_of(elem, name):
    for c in elem.iter():
        if _local(c.tag) == name and (c.text or "").strip():
            return c.text.strip()
    return None


class Frame:
    def __init__(self):
        self.id = None
        self.texts = []
        self.images = []
        self.targets = []

    @property
    def kinds(self):
        out = []
        if self.texts:
            out.append("text")
        if self.images:
            out.append("image")
        if self.targets:
            out.append("target")
        return out


class LiveArea:
    def __init__(self):
        self.style = "a1"
        self.background = None
        self.startup_images = []
        self.gate_label = "Start"
        self.frames = []
        self.targets = []

    @classmethod
    def parse(cls, data):
        live = cls()
        root = ET.fromstring(data)
        live.style = root.get("style", "a1")

        bg = _findall(root, "livearea-background")
        if bg:
            img = _text_of(bg[0], "image")
            if img:
                live.background = img

        for gate in _findall(root, "gate"):
            for si in _findall(gate, "startup-image"):
                if si.text and si.text.strip():
                    live.startup_images.append(si.text.strip())
            label = _text_of(gate, "str")
            if label:
                live.gate_label = label
        if not live.startup_images:
            for si in _findall(root, "startup-image"):
                if si.text and si.text.strip():
                    live.startup_images.append(si.text.strip())

        for frame_el in _findall(root, "frame"):
            frame = Frame()
            frame.id = frame_el.get("id") or frame_el.get("name")
            for str_el in _findall(frame_el, "str"):
                if (str_el.text or "").strip():
                    frame.texts.append(str_el.text.strip())
            for img_el in _findall(frame_el, "image"):
                if (img_el.text or "").strip():
                    frame.images.append(img_el.text.strip())
            for tgt in _findall(frame_el, "target"):
                if (tgt.text or "").strip():
                    frame.targets.append(tgt.text.strip())
                    live.targets.append(tgt.text.strip())
            if frame.texts or frame.images or frame.targets:
                live.frames.append(frame)

        return live


def parse_file(path):
    with open(path, "rb") as fh:
        return LiveArea.parse(fh.read())
