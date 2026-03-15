# -*- coding: utf-8 -*-
"""
Album Generator - Stile Figurine Panini (A4 Portrait)
Genera pagine di album A4 verticali con le locandine disposte come figurine,
con giustidireno.png come sfondo visibile in secondo piano e cornici realistiche.

Supporta:
- Righe e colonne configurabili
- Layout verticale dritto o obliquo (sfalsato)
- Immagini custom per copertina e ultima pagina
- Logo con sfondo bianco nel cerchio (opzionale)
"""

import os
import io
import math
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance


# Semplice cache globale per velocizzare l'anteprima interattiva (evita Image.open ripetuti)
_STK_CACHE = {"path": None, "img": None}

def create_single_sticker(img_path, mask_w_mm=57, mask_h_mm=80, 
                          zoom=1.0, stretch_x=1.0, offset_x=0, offset_y=0, preview_mode=False):
    """
    Elabora una singola immagine per la maschera figurina con parametri interattivi.
    Ritorna un oggetto PIL Image (RGBA) pronto per essere mostrato o salvato.
    Se preview_mode è True, aggiunge un bordo rosso vivace per mostrare i limiti della maschera.
    """
    if not img_path or not os.path.exists(img_path):
        return None
        
    SCALE = 15  # pixel per mm
    mask_w = int(mask_w_mm * SCALE)
    mask_h = int(mask_h_mm * SCALE)
    
    # Check cache
    global _STK_CACHE
    if _STK_CACHE["path"] == img_path:
        original = _STK_CACHE["img"]
    else:
        original = Image.open(img_path).convert("RGBA")
        _STK_CACHE["path"] = img_path
        _STK_CACHE["img"] = original

    orig_w, orig_h = original.size
    
    # Scala base per fittare la larghezza
    base_scale = mask_w / orig_w
    scaled_w = int(orig_w * base_scale)
    scaled_h = int(orig_h * base_scale)
    
    # Applica zoom
    eff_zoom = max(1.0, zoom)
    scaled_w = int(scaled_w * eff_zoom)
    scaled_h = int(scaled_h * eff_zoom)
    
    # Applica stretch orizzontale (max ~1.02, ma lasciato libero per il parametro)
    scaled_w = int(scaled_w * stretch_x)
    
    img_resized = original.resize((scaled_w, scaled_h), Image.LANCZOS)
    
    # === SFONDO SFOCATO (TIPO INSTAGRAM) AL POSTO DEL NERO/TRASPARENTE ===
    cover_ratio = max(mask_w / orig_w, mask_h / orig_h)
    cover_w = int(orig_w * cover_ratio)
    cover_h = int(orig_h * cover_ratio)
    bg_img = original.resize((cover_w, cover_h), Image.LANCZOS)
    
    cx = (cover_w - mask_w) // 2
    cy = (cover_h - mask_h) // 2
    bg_img = bg_img.crop((cx, cy, cx + mask_w, cy + mask_h))
    
    from PIL import ImageFilter, ImageEnhance
    blur_radius = 6 if preview_mode else 18
    bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    enhancer = ImageEnhance.Brightness(bg_img)
    canvas = enhancer.enhance(0.65).convert("RGBA")
    
    # Centratura base + offset utente
    paste_x = (mask_w - scaled_w) // 2 + offset_x
    paste_y = (mask_h - scaled_h) // 2 + offset_y
    
    # Incolla l'immagine ritagliata/scalata sopra lo sfondo sfocato
    canvas.paste(img_resized, (paste_x, paste_y), img_resized)
    
    if preview_mode:
        # Disegna un bounding box rosso spesso per distinguere i bordi in anteprima
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([(0, 0), (mask_w - 1, mask_h - 1)], outline="red", width=8)
    
    return canvas



class AlbumGenerator:
    """Genera un album di figurine stile Panini dalle locandine degli eventi."""

    # --- Dimensioni Pagina A4 PORTRAIT (in pixel a 150 DPI) ---
    PAGE_W = 1240   # ~210mm
    PAGE_H = 1754   # ~297mm
    MARGIN_X = 55
    MARGIN_TOP = 85
    MARGIN_BOTTOM = 45

    # Colori tema Panini classico
    COLOR_PAGE_BG = (20, 40, 75)           # Blu scuro Panini profondo
    COLOR_STICKER_BORDER = (200, 170, 80)  # Oro invecchiato
    COLOR_STICKER_BG = (245, 240, 230)     # Avorio
    COLOR_SHADOW = (15, 30, 55, 120)       # Ombra semi-trasparente
    COLOR_NUMBER_BG = (180, 150, 60)       # Sfondo numero oro scuro
    COLOR_NUMBER_TEXT = (255, 255, 245)     # Testo numero
    COLOR_CAPTION_TEXT = (50, 40, 30)       # Testo didascalia
    COLOR_HEADER_TEXT = (220, 195, 100)     # Testo titolo pagina (oro)

    # Margini interni figurina
    STICKER_PADDING = 8
    BORDER_WIDTH = 4
    CORNER_RADIUS = 12
    SHADOW_OFFSET = 6

    _font_cache = {}
    _resource_cache = {}

    @classmethod
    def _get_cached_resource(cls, path):
        """Carica risorse immagine solo una volta nella vita del worker."""
        if not path or not os.path.exists(path):
            return None
        if path not in cls._resource_cache:
            try:
                cls._resource_cache[path] = Image.open(path).convert("RGBA")
            except Exception:
                cls._resource_cache[path] = None
        return cls._resource_cache[path]

    def __init__(self, bg_image_path="giustidireno.png", logo_path="LogoNOConfiniTrasparente.png",
                 banner_path="bannerprimapaginainalto.png",
                 rows=3, cols=2, layout="verticale",
                 custom_cover_image=None, custom_back_image=None,
                 logo_white_bg=False, logo_cover_white_bg=False, logo_cover_full_page=True,
                 show_banner=True, sticker_fill_mode="trasparente", force_aspect_ratio=False,
                  sticker_height_mm=80,
                  empty_album_mode=False, export_stickers=False, preview_mode=False,
                  show_summary=False, summary_events_per_page=50):
        """
        ...
        """
        self.rows = max(1, min(5, rows))
        self.cols = max(1, min(4, cols))
        self.stickers_per_page = self.rows * self.cols
        self.layout = layout
        self.logo_white_bg = logo_white_bg
        self.logo_cover_white_bg = logo_cover_white_bg
        self.logo_cover_full_page = logo_cover_full_page
        self.show_banner = show_banner
        self.sticker_fill_mode = sticker_fill_mode
        self.force_aspect_ratio = force_aspect_ratio
        self.sticker_height_mm = max(76, min(80, sticker_height_mm))
        self.empty_album_mode = empty_album_mode
        self.export_stickers = export_stickers
        self.preview_mode = preview_mode
        self.show_summary = show_summary
        self.summary_events_per_page = max(30, min(80, summary_events_per_page))
        # --- Caricamento immagini ottimizzato (con cache globale per risorsa base) ---
        self.bg_image = self._get_cached_resource(bg_image_path)
        self.logo_image = self._get_cached_resource(logo_path)
        self.banner_image = self._get_cached_resource(banner_path)
        
        self.custom_cover_image = custom_cover_image
        self.custom_back_image = custom_back_image

    # ---------------------------------------------------------------
    #  UTILITÀ GRAFICHE
    # ---------------------------------------------------------------

    def _get_font(self, size, bold=False):
        """Prova a caricare un font di sistema con CACHE, fallback sul default."""
        cache_key = (size, bold)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
            
        font_names = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
        
        loaded_font = None
        for fn in font_names:
            if os.path.exists(fn):
                try:
                    loaded_font = ImageFont.truetype(fn, size)
                    break
                except Exception:
                    continue
        # Fallback aggressivo: Scarica Roboto da Google Fonts se siamo in ambiente Cloud senza font TTF
        if loaded_font is None:
            fallback_dir = os.path.join(os.getcwd(), "fonts_cache")
            os.makedirs(fallback_dir, exist_ok=True)
            fallback_path = os.path.join(fallback_dir, "Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf")
            
            if not os.path.exists(fallback_path):
                import urllib.request
                try:
                    url = "https://github.com/google/fonts/raw/main/ofl/roboto/Roboto-Bold.ttf" if bold else "https://github.com/google/fonts/raw/main/ofl/roboto/Roboto-Regular.ttf"
                    urllib.request.urlretrieve(url, fallback_path)
                except Exception:
                    pass
            
            try:
                loaded_font = ImageFont.truetype(fallback_path, size)
            except Exception:
                loaded_font = ImageFont.load_default()
            
        self._font_cache[cache_key] = loaded_font
        return loaded_font

    def _wrap_text_by_pixels(self, text, font, max_width, draw):
        """Suddivide il testo in righe basandosi sulla larghezza effettiva in pixel (anti-sbavature su font imprevisti)."""
        if not text:
            return [""]
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            test_line = " ".join(current_line)
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w > max_width:
                if len(current_line) > 1:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(test_line)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    def _prepare_logo(self, logo_img, target_size, white_bg=False):
        """
        Prepara il logo ridimensionato.
        Se white_bg è True, aggiunge un cerchio bianco sotto il logo.
        """
        logo_w, logo_h = logo_img.size
        scale = target_size / max(logo_w, logo_h)
        new_lw = int(logo_w * scale)
        new_lh = int(logo_h * scale)
        logo_resized = logo_img.resize((new_lw, new_lh), Image.LANCZOS)

        if white_bg:
            # Crea un cerchio bianco delle dimensioni del logo
            circle_size = max(new_lw, new_lh) + 10
            circle_canvas = Image.new("RGBA", (circle_size, circle_size), (0, 0, 0, 0))
            circle_draw = ImageDraw.Draw(circle_canvas)
            circle_draw.ellipse([0, 0, circle_size - 1, circle_size - 1],
                               fill=(255, 255, 255, 255))
            paste_x = (circle_size - new_lw) // 2
            paste_y = (circle_size - new_lh) // 2
            circle_canvas.paste(logo_resized, (paste_x, paste_y), logo_resized)
            return circle_canvas
        else:
            return logo_resized

    def _apply_bg_to_page(self, page):
        """
        Applica giustidireno.png come sfondo in secondo piano, ben visibile
        ma non invadente, ripetuto come pattern su tutta la pagina.
        """
        if not self.bg_image:
            return

        bg_w, bg_h = self.bg_image.size

        # Scala il tile a ~160px
        scale = max(160 / bg_w, 160 / bg_h)
        tile_w = int(bg_w * scale)
        tile_h = int(bg_h * scale)
        bg_tile = self.bg_image.resize((tile_w, tile_h), Image.LANCZOS)

        # Rendiamo semi-trasparente ma visibile (~18% opacità)
        alpha = bg_tile.split()[3]
        alpha = alpha.point(lambda p: int(p * 0.18))
        bg_tile.putalpha(alpha)

        # Tile su tutta la pagina con spaziatura
        spacing_x = 30
        spacing_y = 30
        for x in range(15, self.PAGE_W, tile_w + spacing_x):
            for y in range(15, self.PAGE_H, tile_h + spacing_y):
                page.paste(bg_tile, (x, y), bg_tile)

    def _draw_page_frame(self, draw):
        """Disegna la cornice decorativa dorata sulla pagina."""
        # Cornice esterna
        draw.rounded_rectangle(
            [10, 10, self.PAGE_W - 11, self.PAGE_H - 11],
            radius=20, outline=self.COLOR_STICKER_BORDER, width=3
        )
        # Cornice interna
        draw.rounded_rectangle(
            [18, 18, self.PAGE_W - 19, self.PAGE_H - 19],
            radius=16, outline=(self.COLOR_STICKER_BORDER[0], self.COLOR_STICKER_BORDER[1],
                                self.COLOR_STICKER_BORDER[2], 100), width=1
        )

        # Decorazioni angoli
        corner_size = 35
        for cx, cy in [(25, 25), (self.PAGE_W - 25 - corner_size, 25),
                       (25, self.PAGE_H - 25 - corner_size),
                       (self.PAGE_W - 25 - corner_size, self.PAGE_H - 25 - corner_size)]:
            draw.ellipse([cx, cy, cx + corner_size, cy + corner_size],
                        outline=self.COLOR_STICKER_BORDER, width=2)
            draw.ellipse([cx + 8, cy + 8, cx + corner_size - 8, cy + corner_size - 8],
                        fill=self.COLOR_STICKER_BORDER)

    def _create_page_background(self):
        """Crea lo sfondo completo della pagina A4 portrait."""
        page = Image.new("RGBA", (self.PAGE_W, self.PAGE_H), self.COLOR_PAGE_BG)
        self._apply_bg_to_page(page)
        draw = ImageDraw.Draw(page)
        self._draw_page_frame(draw)
        return page

    def _resolve_image_path(self, image_path):
        """
        Risoluzione Robusta (Soluzione Definitiva):
        Normalizza i separatori e tenta di risolvere il path sia come assoluto
        che come relativo alla current working directory.
        """
        if not image_path:
            return None
        
        # Normalizzazione backslash e slash doppie
        clean_path = image_path.replace("\\", "/").replace("//", "/")
        
        # 1. Prova path così com'è (assoluto o relativo alla shell)
        if os.path.exists(clean_path):
            return clean_path
        
        # 2. Prova relativo alla root dell'app (getcwd)
        full_path = os.path.join(os.getcwd(), clean_path)
        if os.path.exists(full_path):
            return full_path
            
        return None

    def _create_sticker(self, image_path, number, location="", date="", sticker_w=500, sticker_h=480, empty=False):
        """
        Crea una singola figurina stile Panini con:
        - Ombra portata
        - Bordo dorato
        - Numero figurina
        - Didascalia con località e data
        - empty=True: disegna solo il borgo e un numero gigante centrale.
        """
        canvas_w = sticker_w + self.SHADOW_OFFSET * 2 + 4
        canvas_h = sticker_h + self.SHADOW_OFFSET * 2 + 4
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # --- Ombra ---
        shadow_rect = [
            self.SHADOW_OFFSET + 3, self.SHADOW_OFFSET + 3,
            sticker_w + self.SHADOW_OFFSET + 3, sticker_h + self.SHADOW_OFFSET + 3
        ]
        draw.rounded_rectangle(shadow_rect, radius=self.CORNER_RADIUS,
                              fill=self.COLOR_SHADOW)

        # --- Sfondo figurina (o Bordo Album Vuoto) ---
        sticker_rect = [2, 2, sticker_w + 2, sticker_h + 2]
        
        # === MODALITA' FIGURINA NORMALE O ALBUM VUOTO (Condivisa) ===
        # Rettangolo base trasparente (sia per trasparente, espansione e opaco)
        # Il colore crema comparirà solo DIETRO all'area dell'immagine in modalità 'opaco'
        alpha_bg = 60 if not empty else 0
        draw.rounded_rectangle(sticker_rect, radius=self.CORNER_RADIUS,
                              fill=(0, 0, 0, alpha_bg),
                              outline=self.COLOR_STICKER_BORDER,
                              width=1 if empty else self.BORDER_WIDTH)
        
        # Area didascalia solida in basso per la leggibilità
        caption_h_calc = min(55, max(35, sticker_h // 10))
        caption_bg_h = caption_h_calc + 14
        caption_bg_bottom = sticker_h + 2 - self.BORDER_WIDTH
        caption_bg_top = caption_bg_bottom - caption_bg_h
        
        draw.rounded_rectangle(
            [self.STICKER_PADDING + 4, caption_bg_top, sticker_w + 2 - self.STICKER_PADDING - 4, caption_bg_bottom],
            radius=6, fill=self.COLOR_STICKER_BG,
            outline=(self.COLOR_STICKER_BORDER[0], self.COLOR_STICKER_BORDER[1], self.COLOR_STICKER_BORDER[2], 120),
            width=1
        )

        # --- Bordo interno decorativo ---
        inner_rect = [
            2 + self.STICKER_PADDING, 2 + self.STICKER_PADDING,
            sticker_w + 2 - self.STICKER_PADDING, sticker_h + 2 - self.STICKER_PADDING
        ]
        draw.rounded_rectangle(inner_rect, radius=self.CORNER_RADIUS - 2,
                              outline=(self.COLOR_STICKER_BORDER[0],
                                      self.COLOR_STICKER_BORDER[1],
                                      self.COLOR_STICKER_BORDER[2], 130),
                              width=1)

        # --- Area immagine ---
        img_x = 2 + self.STICKER_PADDING + self.BORDER_WIDTH + 4
        img_y = 2 + self.STICKER_PADDING + self.BORDER_WIDTH + 4
        img_max_w = sticker_w - (self.STICKER_PADDING + self.BORDER_WIDTH + 4) * 2
        caption_height = min(55, max(35, sticker_h // 10))
        img_max_h = sticker_h - (self.STICKER_PADDING + self.BORDER_WIDTH + 4) * 2 - caption_height

        offset_x, offset_y = img_x, img_y
        draw_w, draw_h = img_max_w, img_max_h

        if empty:
            # Calcola le proporzioni target per mostrare il rettangolo (57x80mm) corretto
            target_ratio = 57.0 / float(self.sticker_height_mm)
            box_w, box_h = img_max_w, img_max_h
            if box_w / box_h > target_ratio:
                box_w = int(box_h * target_ratio)
            else:
                box_h = int(box_w / target_ratio)
            
            draw_w, draw_h = box_w, box_h
            offset_x = img_x + (img_max_w - draw_w) // 2
            offset_y = img_y + (img_max_h - draw_h) // 2

            draw.rectangle(
                [offset_x - 1, offset_y - 1, offset_x + draw_w, offset_y + draw_h],
                outline=(180, 160, 120), width=1
            )
            dash_offset = 2
            draw.rectangle(
                [offset_x + dash_offset, offset_y + dash_offset, offset_x + draw_w - dash_offset, offset_y + draw_h - dash_offset],
                outline=(150, 150, 150, 80), width=1
            )
            
            # Numero gigante per incollaggio
            big_font = self._get_font(int(draw_h * 0.35), bold=True)
            big_txt = str(number)
            bbx = draw.textbbox((0, 0), big_txt, font=big_font)
            bw = bbx[2] - bbx[0]
            bh = bbx[3] - bbx[1]
            draw.text((offset_x + (draw_w - bw) // 2, offset_y + (draw_h - bh) // 2 - int(draw_h * 0.05)),
                      big_txt, fill=(180, 160, 120, 200), font=big_font)
        else:
            # RISOLUZIONE PATH DEFINITIVA
            full_path = self._resolve_image_path(image_path)

            if full_path:
                try:
                    poster = Image.open(full_path).convert("RGBA")
                    p_w, p_h = poster.size
                    
                    # Rilevamento figurina pre-elaborata: se il path contiene 'images_album', assumiamo sia già una figurina finita
                    is_preprocessed_sticker = "images_album" in str(full_path).lower()

                    if self.force_aspect_ratio:
                        # Proporzione configurabile: 57mm larghezza x (76-80)mm altezza
                        target_ratio = 57.0 / float(self.sticker_height_mm)
                        box_w, box_h = img_max_w, img_max_h
                        
                        if box_w / box_h > target_ratio:
                            box_w = int(box_h * target_ratio)
                        else:
                            box_h = int(box_w / target_ratio)
                        
                        # Prova a fittare per larghezza: se l'eccesso in altezza è ≤5%, croppa solo verticalmente
                        fit_w_ratio = box_w / p_w
                        fitted_h = int(p_h * fit_w_ratio)
                        height_excess = (fitted_h - box_h) / box_h if fitted_h > box_h else 0
                        
                        if 0 < height_excess <= 0.05 and not is_preprocessed_sticker:
                            # Micro-crop verticale (max 5%): scala per larghezza, taglia sopra/sotto
                            poster_fitted = poster.resize((box_w, fitted_h), Image.LANCZOS)
                            crop_top = (fitted_h - box_h) // 2
                            poster_to_draw = poster_fitted.crop((0, crop_top, box_w, crop_top + box_h))
                            draw_w, draw_h = box_w, box_h
                        else:
                            # Fit completo dentro il box (nessun crop)
                            ratio = min(box_w / p_w, box_h / p_h)
                            new_pw = int(p_w * ratio)
                            new_ph = int(p_h * ratio)
                            poster_resized = poster.resize((new_pw, new_ph), Image.LANCZOS)

                            # Applica espansione solo se NON è già una figurina pre-elaborata
                            if self.sticker_fill_mode == "espansione" and (new_pw < box_w or new_ph < box_h) and not is_preprocessed_sticker:
                                # === ESPANSIONE INTELLIGENTE (sfocatura) ===
                                cover_ratio = max(box_w / p_w, box_h / p_h)
                                cover_w = int(p_w * cover_ratio)
                                cover_h = int(p_h * cover_ratio)
                                bg_img = poster.resize((cover_w, cover_h), Image.LANCZOS)
                                
                                cx = (cover_w - box_w) // 2
                                cy = (cover_h - box_h) // 2
                                bg_img = bg_img.crop((cx, cy, cx + box_w, cy + box_h))
                                
                                blur_radius = 6 if self.preview_mode else 18
                                bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                                enhancer = ImageEnhance.Brightness(bg_img)
                                bg_img = enhancer.enhance(0.65)
                                
                                final_poster = bg_img.convert("RGBA")
                                off_p_x = (box_w - new_pw) // 2
                                off_p_y = (box_h - new_ph) // 2
                                final_poster.paste(poster_resized, (off_p_x, off_p_y), poster_resized)
                            else:
                                # Trasparente o Opaco (o se è già una figurina): canvas vuoto per l'immagine
                                if self.sticker_fill_mode == "opaco" and not is_preprocessed_sticker:
                                    fill_color = self.COLOR_STICKER_BG  # Riempi di crema
                                else:
                                    fill_color = (0, 0, 0, 0) # Trasparente
                                
                                final_poster = Image.new("RGBA", (box_w, box_h), fill_color)
                                off_p_x = (box_w - new_pw) // 2
                                off_p_y = (box_h - new_ph) // 2
                                final_poster.paste(poster_resized, (off_p_x, off_p_y), poster_resized)
                            
                            poster_to_draw = final_poster
                            draw_w, draw_h = box_w, box_h

                    else:
                        # Comportamento classico: sfrutta massimo spazio
                        box_w, box_h = img_max_w, img_max_h
                        ratio = min(box_w / p_w, box_h / p_h)
                        new_pw = int(p_w * ratio)
                        new_ph = int(p_h * ratio)
                        poster_resized = poster.resize((new_pw, new_ph), Image.LANCZOS)
                        
                        if self.sticker_fill_mode == "espansione" and (new_pw < box_w or new_ph < box_h) and not is_preprocessed_sticker:
                            # === ESPANSIONE INTELLIGENTE (sfocatura) ===
                            cover_ratio = max(box_w / p_w, box_h / p_h)
                            cover_w = int(p_w * cover_ratio)
                            cover_h = int(p_h * cover_ratio)
                            bg_img = poster.resize((cover_w, cover_h), Image.LANCZOS)
                            
                            cx = (cover_w - box_w) // 2
                            cy = (cover_h - box_h) // 2
                            bg_img = bg_img.crop((cx, cy, cx + box_w, cy + box_h))
                            
                            blur_radius = 6 if self.preview_mode else 18
                            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                            enhancer = ImageEnhance.Brightness(bg_img)
                            bg_img = enhancer.enhance(0.65)
                            
                            final_poster = bg_img.convert("RGBA")
                            off_p_x = (box_w - new_pw) // 2
                            off_p_y = (box_h - new_ph) // 2
                            final_poster.paste(poster_resized, (off_p_x, off_p_y), poster_resized)
                            
                        else:
                            # Trasparente o Opaco (o se è già una figurina): canvas vuoto per l'immagine
                            if self.sticker_fill_mode == "opaco" and not is_preprocessed_sticker:
                                fill_color = self.COLOR_STICKER_BG  # Riempi di crema
                            else:
                                fill_color = (0, 0, 0, 0) # Trasparente
                                
                            final_poster = Image.new("RGBA", (box_w, box_h), fill_color)
                            off_p_x = (box_w - new_pw) // 2
                            off_p_y = (box_h - new_ph) // 2
                            final_poster.paste(poster_resized, (off_p_x, off_p_y), poster_resized)
                            
                        poster_to_draw = final_poster
                        draw_w, draw_h = box_w, box_h

                    offset_x = img_x + (img_max_w - draw_w) // 2
                    offset_y = img_y + (img_max_h - draw_h) // 2

                    draw.rectangle(
                        [offset_x - 1, offset_y - 1, offset_x + draw_w, offset_y + draw_h],
                        outline=(180, 160, 120), width=1
                    )
                    
                    # Incollo la vera figurina
                    canvas.paste(poster_to_draw, (offset_x, offset_y), poster_to_draw)
                    
                except Exception:
                    self._draw_placeholder(draw, img_x, img_y, img_max_w, img_max_h)
            else:
                self._draw_placeholder(draw, img_x, img_y, img_max_w, img_max_h)

        # --- Numero Figurina (Badge dorato) ---
        badge_size = max(24, min(34, sticker_w // 16))
        badge_x = 2 + self.STICKER_PADDING + 6
        badge_y = sticker_h + 2 - caption_height - 2
        draw.ellipse([badge_x + 2, badge_y + 2, badge_x + badge_size + 2, badge_y + badge_size + 2],
                    fill=(30, 25, 15, 80))
        draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                    fill=self.COLOR_NUMBER_BG, outline=self.COLOR_STICKER_BORDER, width=2)
        draw.ellipse([badge_x + 4, badge_y + 4, badge_x + badge_size - 4, badge_y + badge_size - 4],
                    outline=(255, 240, 180, 150), width=1)
        font_num = self._get_font(max(10, badge_size // 2), bold=True)
        num_text = str(number)
        bbox = draw.textbbox((0, 0), num_text, font=font_num)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((badge_x + (badge_size - tw) // 2, badge_y + (badge_size - th) // 2 - 1),
                 num_text, fill=self.COLOR_NUMBER_TEXT, font=font_num)

        # --- Didascalia ---
        caption_y = sticker_h + 2 - caption_height + 4
        font_size_loc = max(9, min(13, sticker_w // 42))
        font_size_date = max(7, min(10, sticker_w // 55))
        font_loc = self._get_font(font_size_loc, bold=True)
        font_date = self._get_font(font_size_date)

        caption_x = badge_x + badge_size + 8

        loc_text = location.strip().upper() if location else "EVENTO"
        max_chars = max(12, sticker_w // 20)
        if len(loc_text) > max_chars:
            loc_text = loc_text[:max_chars - 2] + "..."
        draw.text((caption_x, caption_y + 3), loc_text,
                 fill=self.COLOR_CAPTION_TEXT, font=font_loc)

        date_text = date.strip() if date else ""
        if date_text:
            draw.text((caption_x, caption_y + 3 + font_size_loc + 4), date_text,
                     fill=(120, 110, 90), font=font_date)

        # Linea separatrice decorativa
        line_y = caption_y - 4
        draw.line([(img_x, line_y), (sticker_w + 2 - self.STICKER_PADDING - 4, line_y)],
                 fill=(self.COLOR_STICKER_BORDER[0], self.COLOR_STICKER_BORDER[1],
                       self.COLOR_STICKER_BORDER[2], 100), width=1)

        return canvas, (offset_x, offset_y, draw_w, draw_h)

    def _draw_placeholder(self, draw, x, y, w, h):
        """Disegna un placeholder quando l'immagine non è disponibile."""
        draw.rectangle([x, y, x + w, y + h], fill=(220, 215, 205), outline=(180, 170, 150))
        font_ph = self._get_font(12)
        draw.text((x + 10, y + h // 2 - 10), "Immagine\nnon disponibile",
                 fill=(150, 140, 130), font=font_ph)

    def _page_to_rgb(self, page):
        """Converte pagina RGBA in RGB per salvataggio."""
        page_rgb = Image.new("RGB", page.size, self.COLOR_PAGE_BG)
        page_rgb.paste(page, mask=page.split()[3])
        return page_rgb

    # ---------------------------------------------------------------
    #  COPERTINA (PRIMA PAGINA)
    # ---------------------------------------------------------------

    def generate_cover(self, total_events, output_dir="output"):
        """Genera la copertina: se c'è immagine custom → full-bleed senza testi; altrimenti layout classico."""
        os.makedirs(output_dir, exist_ok=True)

        cover = Image.new("RGBA", (self.PAGE_W, self.PAGE_H), self.COLOR_PAGE_BG)
        self._apply_bg_to_page(cover)
        draw = ImageDraw.Draw(cover)

        # -- MODALITA FULL-BLEED (immagine custom caricata) --
        if self.custom_cover_image:
            # Area interna alla cornice (margini 30px per lato)
            frame_margin = 30
            inner_x = frame_margin
            inner_y = frame_margin
            inner_w = self.PAGE_W - frame_margin * 2
            inner_h = self.PAGE_H - frame_margin * 2

            ci_w, ci_h = self.custom_cover_image.size
            # Scala cover-mode: riempie completamente l'area interna
            ratio = max(inner_w / ci_w, inner_h / ci_h)
            new_ci_w = int(ci_w * ratio)
            new_ci_h = int(ci_h * ratio)
            cover_resized = self.custom_cover_image.resize((new_ci_w, new_ci_h), Image.LANCZOS)

            # Centra e ritaglia per coprire esattamente l'area interna
            crop_x = (new_ci_w - inner_w) // 2
            crop_y = (new_ci_h - inner_h) // 2
            cover_cropped = cover_resized.crop((crop_x, crop_y, crop_x + inner_w, crop_y + inner_h))
            cover.paste(cover_cropped, (inner_x, inner_y), cover_cropped)

            # Cornice lusso (disegnata SOPRA l'immagine)
            draw.rounded_rectangle([15, 15, self.PAGE_W - 16, self.PAGE_H - 16],
                                  radius=25, outline=self.COLOR_STICKER_BORDER, width=5)
            draw.rounded_rectangle([25, 25, self.PAGE_W - 26, self.PAGE_H - 26],
                                  radius=20, outline=(self.COLOR_STICKER_BORDER[0],
                                                       self.COLOR_STICKER_BORDER[1],
                                                       self.COLOR_STICKER_BORDER[2], 100), width=2)

            # Decorazioni angoli
            corner_s = 50
            for cx, cy in [(30, 30), (self.PAGE_W - 30 - corner_s, 30),
                           (30, self.PAGE_H - 30 - corner_s),
                           (self.PAGE_W - 30 - corner_s, self.PAGE_H - 30 - corner_s)]:
                draw.rounded_rectangle([cx, cy, cx + corner_s, cy + corner_s],
                                      radius=8, outline=self.COLOR_STICKER_BORDER, width=2)
                draw.rounded_rectangle([cx + 6, cy + 6, cx + corner_s - 6, cy + corner_s - 6],
                                      radius=4, fill=self.COLOR_NUMBER_BG)

            # NESSUN testo sulla copertina full-bleed: verranno spostati nella inner cover

        else:
            # -- MODALITA CLASSICA (logo / senza immagine custom) --
            # Cornice lusso
            draw.rounded_rectangle([15, 15, self.PAGE_W - 16, self.PAGE_H - 16],
                                  radius=25, outline=self.COLOR_STICKER_BORDER, width=5)
            draw.rounded_rectangle([25, 25, self.PAGE_W - 26, self.PAGE_H - 26],
                                  radius=20, outline=(self.COLOR_STICKER_BORDER[0],
                                                       self.COLOR_STICKER_BORDER[1],
                                                       self.COLOR_STICKER_BORDER[2], 100), width=2)

            # Decorazioni angoli
            corner_s = 50
            for cx, cy in [(30, 30), (self.PAGE_W - 30 - corner_s, 30),
                           (30, self.PAGE_H - 30 - corner_s),
                           (self.PAGE_W - 30 - corner_s, self.PAGE_H - 30 - corner_s)]:
                draw.rounded_rectangle([cx, cy, cx + corner_s, cy + corner_s],
                                      radius=8, outline=self.COLOR_STICKER_BORDER, width=2)
                draw.rounded_rectangle([cx + 6, cy + 6, cx + corner_s - 6, cy + corner_s - 6],
                                      radius=4, fill=self.COLOR_NUMBER_BG)

            # === BANNER in cima ===
            current_y = 35
            if self.show_banner and self.banner_image:
                ban_w, ban_h = self.banner_image.size
                target_ban_w = self.PAGE_W - 70
                ban_scale = target_ban_w / ban_w
                new_ban_w = int(ban_w * ban_scale)
                new_ban_h = int(ban_h * ban_scale)
                banner_resized = self.banner_image.resize((new_ban_w, new_ban_h), Image.LANCZOS)
                bx = (self.PAGE_W - new_ban_w) // 2
                cover.paste(banner_resized, (bx, current_y), banner_resized)
                current_y += new_ban_h + 15
            else:
                current_y = 60

            # === TITOLO ===
            font_title = self._get_font(92, bold=True)
            title = "ALBUM"
            bbox = draw.textbbox((0, 0), title, font=font_title)
            tw = bbox[2] - bbox[0]
            draw.text(((self.PAGE_W - tw) // 2, current_y), title,
                     fill=self.COLOR_HEADER_TEXT, font=font_title)
            current_y += 140

            # Sottotitolo
            font_sub = self._get_font(26, bold=True)
            subtitle = "GIUSTO DIRE NO"
            bbox2 = draw.textbbox((0, 0), subtitle, font=font_sub)
            sw = bbox2[2] - bbox2[0]
            draw.text(((self.PAGE_W - sw) // 2, current_y), subtitle,
                     fill=(255, 255, 255), font=font_sub)
            current_y += 40

            # Linea decorativa
            line_margin = 120
            draw.line([(line_margin, current_y), (self.PAGE_W - line_margin, current_y)],
                     fill=self.COLOR_STICKER_BORDER, width=2)
            mid_x = self.PAGE_W // 2
            diamond = 8
            draw.polygon([(mid_x, current_y - diamond), (mid_x + diamond, current_y),
                          (mid_x, current_y + diamond), (mid_x - diamond, current_y)],
                        fill=self.COLOR_STICKER_BORDER)
            current_y += 20

            # === LOGO ===
            footer_zone = 200
            available_h = self.PAGE_H - current_y - footer_zone
            available_w = self.PAGE_W - 80

            if self.logo_image:
                target_size = min(available_w, available_h) - 40
                if not self.logo_cover_full_page and target_size > 400:
                    target_size = 400
                logo_prepared = self._prepare_logo(self.logo_image, target_size, white_bg=self.logo_cover_white_bg)
                cx = (self.PAGE_W - logo_prepared.size[0]) // 2
                cy = current_y + (available_h - logo_prepared.size[1]) // 2
                cover.paste(logo_prepared, (cx, cy), logo_prepared)

            # === Testi footer (solo in modalità classica) ===
            footer_start_y = self.PAGE_H - footer_zone + 10

            font_ed = self._get_font(9)
            ed_text = "Referendum Giustizia 2026"
            bbox_ed = draw.textbbox((0, 0), ed_text, font=font_ed)
            ew = bbox_ed[2] - bbox_ed[0]
            draw.text(((self.PAGE_W - ew) // 2, footer_start_y), ed_text,
                     fill=(180, 170, 140), font=font_ed)

            font_desc = self._get_font(14)
            desc_lines = [
                "Tutti gli eventi del Comitato",
                "Coordinamento Liguria e Massa",
                "per il referendum sulla Giustizia"
            ]
            desc_y = footer_start_y + 35
            for line in desc_lines:
                bbox_l = draw.textbbox((0, 0), line, font=font_desc)
                lwd = bbox_l[2] - bbox_l[0]
                draw.text(((self.PAGE_W - lwd) // 2, desc_y), line,
                         fill=(150, 142, 120), font=font_desc)
                desc_y += 22

            draw.line([(line_margin, desc_y + 10), (self.PAGE_W - line_margin, desc_y + 10)],
                     fill=(self.COLOR_STICKER_BORDER[0], self.COLOR_STICKER_BORDER[1],
                           self.COLOR_STICKER_BORDER[2], 120), width=1)

            font_footer = self._get_font(12)
            footer = "Edizione Speciale 2026 — Comitato Giusto Dire No"
            bbox5 = draw.textbbox((0, 0), footer, font=font_footer)
            fw = bbox5[2] - bbox5[0]
            draw.text(((self.PAGE_W - fw) // 2, self.PAGE_H - 70),
                     footer, fill=(110, 105, 90), font=font_footer)

            footer2 = "Coordinamento Liguria e Massa"
            bbox6 = draw.textbbox((0, 0), footer2, font=font_footer)
            fw2 = bbox6[2] - bbox6[0]
            draw.text(((self.PAGE_W - fw2) // 2, self.PAGE_H - 48),
                     footer2, fill=(95, 90, 75), font=font_footer)

        # Salva a 300 DPI per stampa tipografica
        cover_rgb = self._page_to_rgb(cover)
        cover_rgb = cover_rgb.resize((2480, 3508), Image.LANCZOS)
        cover_path = os.path.join(output_dir, "album_000_cover.png")
        cover_rgb.save(cover_path, "PNG", quality=95)
        return cover_path

    # ---------------------------------------------------------------
    #  SECONDA PAGINA — RETRO COPERTINA (Inner Cover)
    # ---------------------------------------------------------------

    def generate_inner_cover(self, total_events, output_dir="output"):
        """
        Genera la seconda pagina (retro copertina interna).
        Contiene titolo album, sottotitoli e testi che normalmente starebbero
        sulla copertina, ma vengono spostati qui quando la copertina è full-bleed.
        """
        os.makedirs(output_dir, exist_ok=True)

        page = Image.new("RGBA", (self.PAGE_W, self.PAGE_H), self.COLOR_PAGE_BG)
        self._apply_bg_to_page(page)
        draw = ImageDraw.Draw(page)
        self._draw_page_frame(draw)

        # === Logo piccolo in alto ===
        current_y = 100
        if self.logo_image:
            logo_prepared = self._prepare_logo(self.logo_image, 200, white_bg=self.logo_cover_white_bg)
            lx = (self.PAGE_W - logo_prepared.size[0]) // 2
            page.paste(logo_prepared, (lx, current_y), logo_prepared)
            current_y += logo_prepared.size[1] + 30

        # === Linea decorativa superiore ===
        line_margin = 120
        draw.line([(line_margin, current_y), (self.PAGE_W - line_margin, current_y)],
                 fill=self.COLOR_STICKER_BORDER, width=2)
        mid_x = self.PAGE_W // 2
        diamond = 8
        draw.polygon([(mid_x, current_y - diamond), (mid_x + diamond, current_y),
                      (mid_x, current_y + diamond), (mid_x - diamond, current_y)],
                    fill=self.COLOR_STICKER_BORDER)
        current_y += 40

        # === TITOLO grande ===
        font_title = self._get_font(82, bold=True)
        title = "ALBUM"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((self.PAGE_W - tw) // 2, current_y), title,
                 fill=self.COLOR_HEADER_TEXT, font=font_title)
        current_y += 120

        # === SOTTOTITOLO ===
        font_sub = self._get_font(30, bold=True)
        subtitle = "Campagna Referendaria Giusto Dire NO!!"
        bbox2 = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw = bbox2[2] - bbox2[0]
        draw.text(((self.PAGE_W - sw) // 2, current_y), subtitle,
                 fill=(255, 255, 255), font=font_sub)
        current_y += 55

        # === Linea decorativa ===
        draw.line([(line_margin, current_y), (self.PAGE_W - line_margin, current_y)],
                 fill=self.COLOR_STICKER_BORDER, width=2)
        draw.polygon([(mid_x, current_y - diamond), (mid_x + diamond, current_y),
                      (mid_x, current_y + diamond), (mid_x - diamond, current_y)],
                    fill=self.COLOR_STICKER_BORDER)
        current_y += 50

        # Salva a 300 DPI
        page_rgb = self._page_to_rgb(page)
        page_rgb = page_rgb.resize((2480, 3508), Image.LANCZOS)
        inner_path = os.path.join(output_dir, "album_001_inner_cover.png")
        page_rgb.save(inner_path, "PNG", quality=95)
        return inner_path

    # ---------------------------------------------------------------
    #  ULTIMA PAGINA (CHIUSURA)
    # ---------------------------------------------------------------

    def generate_back_cover(self, total_events, output_dir="output"):
        """Genera l'ultima pagina con logo centrale e info collezione in basso."""
        os.makedirs(output_dir, exist_ok=True)

        back = Image.new("RGBA", (self.PAGE_W, self.PAGE_H), self.COLOR_PAGE_BG)
        self._apply_bg_to_page(back)
        draw = ImageDraw.Draw(back)
        self._draw_page_frame(draw)

        # === Testo di ringraziamento in alto ===
        font_testo = self._get_font(32)
        colore_oro = (218, 165, 32)
        colore_ombra = (20, 20, 20, 180)
        max_width_px = 900

        body_lines = [
            "Quest'album raccoglie tutti gli eventi organizzati",
            "dal Comitato \"Giusto Dire No\"",
            "per il Referendum Costituzionale sulla Giustizia.",
            "",
            "Coordinamento Liguria e Massa",
            "",
            "Ogni figurina rappresenta un incontro,",
            "un dibattito, un momento di partecipazione",
            "democratica sul territorio.",
            "",
            "Grazie a tutti i volontari e ai cittadini",
            "che hanno partecipato!",
        ]

        body_y = 150
        for paragrafo in body_lines:
            if not paragrafo:
                body_y += 35
                continue

            righe_wrappate = self._wrap_text_by_pixels(paragrafo, font_testo, max_width_px, draw)
            for riga in righe_wrappate:
                bbox = draw.textbbox((0, 0), riga, font=font_testo)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = (self.PAGE_W - tw) // 2
                
                # Ombra del testo
                draw.text((x + 2, body_y + 2), riga, fill=colore_ombra, font=font_testo)
                draw.text((x, body_y), riga, fill=colore_oro, font=font_testo)
                body_y += th + 15

        # === LOGO === (spostato più in basso e centrato rispetto al footer)
        back_img_source = self.custom_back_image if self.custom_back_image else self.logo_image

        if back_img_source:
            target_size = 350
            logo_prepared = self._prepare_logo(back_img_source, target_size, white_bg=self.logo_white_bg)

            # Calcola spazio tra testo e footer
            space_between = (self.PAGE_H - 120) - body_y
            
            bx = (self.PAGE_W - logo_prepared.size[0]) // 2
            # Centra verticalmente nello spazio libero rimasto, un po' più giù
            by = body_y + (space_between - logo_prepared.size[1]) // 2
            if by < body_y + 20: by = body_y + 20 # margine minimo dal testo
            
            back.paste(logo_prepared, (bx, by), logo_prepared)
        # Footer
        font_footer = self._get_font(24)
        footer = "© 2026 Comitato Giusto Dire No — Coordinamento Liguria e Massa"
        bbox5 = draw.textbbox((0, 0), footer, font=font_footer)
        fw = bbox5[2] - bbox5[0]
        draw.text(((self.PAGE_W - fw) // 2, self.PAGE_H - 110),
                 footer, fill=(100, 95, 80), font=font_footer)

        footer2 = "Referendum Giustizia — Edizione Speciale 2026"
        bbox6 = draw.textbbox((0, 0), footer2, font=font_footer)
        fw2 = bbox6[2] - bbox6[0]
        draw.text(((self.PAGE_W - fw2) // 2, self.PAGE_H - 75),
                 footer2, fill=(90, 85, 70), font=font_footer)

        # Salva a 300 DPI per stampa tipografica
        back_rgb = self._page_to_rgb(back)
        back_rgb = back_rgb.resize((2480, 3508), Image.LANCZOS)
        back_path = os.path.join(output_dir, "album_zzz_back.png")
        back_rgb.save(back_path, "PNG", quality=95)
        return back_path

    def generate_logo_page(self, output_dir, filename="album_page_guard.png", is_front=False):
        """Genera una pagina di 'cartone' (sfondo album) con il logo centrale (e opzionalmente un testo)."""
        import textwrap
        page = Image.new("RGBA", (self.PAGE_W, self.PAGE_H), self.COLOR_PAGE_BG)
        self._apply_bg_to_page(page)
        
        draw = ImageDraw.Draw(page)
        self._draw_page_frame(draw)
        
        # Prepara il logo (sempre al centro, in trasparenza se c'è testo per fare da sfondo)
        if self.logo_image:
            logo = self._prepare_logo(self.logo_image, target_size=900)
            if is_front:
                # Applica una forte trasparenza per farlo stare in secondo piano come filigrana
                alpha = logo.split()[3]
                alpha = alpha.point(lambda p: p * 0.15)
                logo.putalpha(alpha)
                
            lx = (self.PAGE_W - logo.size[0]) // 2
            ly = (self.PAGE_H - logo.size[1]) // 2
            page.paste(logo, (lx, ly), logo)
            
        if is_front:
            current_y = 200
            testo_raw = [
                "Il 22 e 23 marzo non sono soltanto due date sul calendario. Sono un passaggio di coscienza civile.",
                "",
                "In queste settimane ho visto magistrati, pubblici ministeri, avvocati ed ex magistrati metterci la faccia, la voce, la dignità delle loro toghe per difendere qualcosa che appartiene a tutti: la giustizia come pilastro della nostra democrazia e della nostra Costituzione.",
                "",
                "A loro va un pensiero pieno di rispetto. Non per una battaglia di parte, ma per aver ricordato che la giustizia non è un terreno da smontare pezzo dopo pezzo, bensì una casa comune da custodire.",
                "",
                "C’è qualcosa di profondamente romantico — nel senso più alto del termine — nella speranza civile: credere che le istituzioni possano ancora essere difese con la parola, con lo studio, con la partecipazione. Credere che la Costituzione non sia un libro antico, ma una promessa viva.",
                "",
                "Se il 22 e 23 marzo gli italiani sceglieranno di difendere questi principi, allora potrà davvero cominciare una nuova primavera: una primavera di libertà, di legalità, di fiducia nella democrazia.",
                "",
                "Una primavera antifascista, nel senso più autentico della nostra Repubblica: quello di un Paese che non ha paura della giustizia, ma la protegge.",
                "",
                "Massimiliano Ferrando"
            ]
            
            font_testo = self._get_font(32)
            font_firma = self._get_font(42, bold=True)
            colore_oro = (218, 165, 32)
            colore_ombra = (20, 20, 20, 180)
            
            max_width_px = 950 # Circa 145px di margine ai lati
            
            for i, paragrafo in enumerate(testo_raw):
                if not paragrafo:
                    current_y += 28
                    continue
                
                is_firma = (i == len(testo_raw) - 1)
                font_da_usare = font_firma if is_firma else font_testo
                if is_firma:
                    current_y += 50
                
                righe_wrappate = self._wrap_text_by_pixels(paragrafo, font_da_usare, max_width_px, draw)
                for riga in righe_wrappate:
                    bbox = draw.textbbox((0, 0), riga, font=font_da_usare)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                    
                    if is_firma:
                        x = self.PAGE_W - tw - 150
                    else:
                        x = (self.PAGE_W - tw) // 2
                    
                    # Ombra del testo per spiccare
                    draw.text((x + 2, current_y + 2), riga, fill=colore_ombra, font=font_da_usare)
                    draw.text((x, current_y), riga, fill=colore_oro, font=font_da_usare)
                    current_y += th + 12
        else:
            # Aggiungi un titolo decorativo per non farla sembrare vuota
            draw.text((self.PAGE_W // 2 - 100, self.PAGE_H - 150), 
                      "COLLEZIONE 2026", fill=(100, 95, 80), 
                      font=self._get_font(18, bold=True))

        # Salva a 300 DPI
        page_rgb = self._page_to_rgb(page)
        page_rgb = page_rgb.resize((2480, 3508), Image.LANCZOS)
        path = os.path.join(output_dir, filename)
        page_rgb.save(path, "PNG", quality=95)
        return path

    def generate_blank_page(self, output_dir, filename="album_page_blank.png"):
        """Genera una pagina di 'carta' vuota (con header e footer) senza figurine."""
        page = self._create_page_background()
        draw = ImageDraw.Draw(page)
        
        # Header
        font_header = self._get_font(20, bold=True)
        header_text = "GIUSTO DIRE NO  —  ALBUM EVENTI"
        bbox = draw.textbbox((0, 0), header_text, font=font_header)
        header_w = bbox[2] - bbox[0]
        draw.text(((self.PAGE_W - header_w) // 2, 28), header_text, fill=self.COLOR_HEADER_TEXT, font=font_header)
        
        # Footer
        font_footer = self._get_font(9)
        footer_text = "© Comitato Giusto Dire No — Collezione Completa Eventi — Coordinamento Liguria e Massa"
        bbox3 = draw.textbbox((0, 0), footer_text, font=font_footer)
        footer_w = bbox3[2] - bbox3[0]
        draw.text(((self.PAGE_W - footer_w) // 2, self.PAGE_H - 32), footer_text, fill=(100, 95, 80), font=font_footer)
        
        # Salva a 300 DPI
        page_rgb = self._page_to_rgb(page)
        page_rgb = page_rgb.resize((2480, 3508), Image.LANCZOS)
        path = os.path.join(output_dir, filename)
        page_rgb.save(path, "PNG", quality=95)
        return path

    def generate_summary_pages(self, events, output_dir="output"):
        """
        Genera pagine riepilogative con l'elenco di tutti gli eventi in ordine cronologico.
        Layout a DUE COLONNE: ogni colonna mostra #, Data, Ora, Localita', Indirizzo.
        self.summary_events_per_page e' la soglia MINIMA di eventi per pagina;
        il sistema puo' aumentarla per riempire meglio le pagine ed evitare vuoti.
        L'altezza delle righe viene calcolata una sola volta sulla prima pagina
        (la piu' piena) e mantenuta identica su tutte le pagine successive.
        """
        if not events:
            return []

        os.makedirs(output_dir, exist_ok=True)

        # 1. Recupera date e mantieni indice originale (numero figurina)
        indexed_events = []
        from datetime import datetime
        import dateparser

        for i, ev in enumerate(events):
            dt = ev.get('_dt')
            if not dt:
                d_str = ev.get('date', '').strip()
                try:
                    dt = dateparser.parse(d_str, languages=['it', 'en']) or datetime.max
                except:
                    dt = datetime.max
            indexed_events.append((ev, dt, i + 1))

        # 2. Ordina per data cronologica
        indexed_events.sort(key=lambda x: x[1])

        total = len(indexed_events)

        # 3. Distribuzione intelligente
        #    Il valore dello slider e' la soglia minima. Proviamo a ridurre il
        #    numero di pagine (aumentando gli eventi per pagina) purche' le righe
        #    restino fisicamente leggibili (altezza minima 22px).
        margin_x = 50
        col_gap = 20
        start_y = 140
        header_h = 36
        footer_margin = 50
        usable_h = self.PAGE_H - start_y - footer_margin
        min_row_h = 22

        # Massimo eventi che entrano fisicamente in una pagina (2 colonne)
        max_rows_per_col = (usable_h - header_h) // min_row_h
        max_events_physical = max_rows_per_col * 2

        min_per_page = self.summary_events_per_page  # soglia minima dall'utente

        # Calcola il numero di pagine partendo dal massimo necessario
        # e prova a ridurlo finche' gli eventi per pagina restano nel limite fisico
        total_pages = math.ceil(total / min_per_page)
        while total_pages > 1:
            candidate = math.ceil(total / (total_pages - 1))
            if candidate <= max_events_physical:
                total_pages -= 1
            else:
                break
        # Anche con 1 pagina, verifica che ci stia
        if total_pages == 1 and total > max_events_physical:
            total_pages = math.ceil(total / max_events_physical)

        actual_per_page = math.ceil(total / total_pages)

        # 4. Calcola altezza riga UNA VOLTA (basata sulla pagina piu' piena = actual_per_page)
        rows_first_page = math.ceil(actual_per_page / 2)
        row_h = max(min_row_h, (usable_h - header_h) // rows_first_page)

        # 5. Larghezze colonne
        total_col_w = (self.PAGE_W - margin_x * 2 - col_gap) // 2
        # Sotto-colonne: #, DATA, ORA, LOCALITA', INDIRIZZO
        sub_num_w = 28
        sub_date_w = 105
        sub_ora_w = 38
        sub_loc_w = 115
        sub_addr_w = total_col_w - sub_num_w - sub_date_w - sub_ora_w - sub_loc_w

        summary_paths = []

        font_title = self._get_font(24, bold=True)
        font_sub = self._get_font(11)
        font_col_header = self._get_font(11, bold=True)
        font_row = self._get_font(11)
        font_num = self._get_font(11, bold=True)

        colore_oro = (218, 165, 32)
        colore_testo = (230, 225, 210)
        colore_dim = (170, 162, 140)
        colore_riga_alt = (35, 55, 95, 80)

        for p_idx in range(total_pages):
            page = self._create_page_background()
            draw = ImageDraw.Draw(page)

            # Header Pagina
            h_text = "ELENCO RIEPILOGATIVO EVENTI"
            hb = draw.textbbox((0, 0), h_text, font=font_title)
            draw.text(((self.PAGE_W - (hb[2] - hb[0])) // 2, 30), h_text,
                      fill=self.COLOR_HEADER_TEXT, font=font_title)

            pg_label = f"Pagina {p_idx + 1} di {total_pages}  —  {total} eventi totali"
            plb = draw.textbbox((0, 0), pg_label, font=font_sub)
            draw.text(((self.PAGE_W - (plb[2] - plb[0])) // 2, 62), pg_label,
                      fill=(160, 150, 120), font=font_sub)

            # Linea decorativa
            draw.line([(margin_x, start_y - 18), (self.PAGE_W - margin_x, start_y - 18)],
                      fill=colore_oro, width=1)

            # Eventi per questa pagina
            page_start = p_idx * actual_per_page
            page_end = min(page_start + actual_per_page, total)
            page_events = indexed_events[page_start:page_end]

            # Dividi eventi in due colonne (sx prende il ceil)
            mid = math.ceil(len(page_events) / 2)
            col_left_events = page_events[:mid]
            col_right_events = page_events[mid:]

            for col_idx, col_events in enumerate([col_left_events, col_right_events]):
                cx = margin_x + col_idx * (total_col_w + col_gap)

                # Testata colonna
                draw.rectangle(
                    [cx, start_y, cx + total_col_w, start_y + header_h],
                    fill=(30, 50, 90), outline=colore_oro, width=1
                )
                hdr_labels = ["#", "DATA", "ORA", "LOCALITA'", "INDIRIZZO"]
                hdr_offsets = [
                    4,
                    sub_num_w + 4,
                    sub_num_w + sub_date_w + 2,
                    sub_num_w + sub_date_w + sub_ora_w + 4,
                    sub_num_w + sub_date_w + sub_ora_w + sub_loc_w + 4
                ]
                for hi, hl in enumerate(hdr_labels):
                    draw.text(
                        (cx + hdr_offsets[hi], start_y + (header_h - 12) // 2),
                        hl, fill=colore_oro, font=font_col_header
                    )

                cy = start_y + header_h

                for row_i, (ev, dt, num) in enumerate(col_events):
                    # Riga alterna
                    if row_i % 2 == 1:
                        draw.rectangle(
                            [cx, cy, cx + total_col_w, cy + row_h],
                            fill=colore_riga_alt
                        )
                    # Linea separatrice
                    draw.line(
                        [(cx, cy + row_h), (cx + total_col_w, cy + row_h)],
                        fill=(80, 90, 120, 80), width=1
                    )

                    text_y = cy + (row_h - 12) // 2

                    # -- # (numero figurina) --
                    ns = str(num)
                    nb = draw.textbbox((0, 0), ns, font=font_num)
                    draw.text(
                        (cx + (sub_num_w - (nb[2] - nb[0])) // 2, text_y),
                        ns, fill=colore_oro, font=font_num
                    )

                    # -- DATA --
                    ds = ev.get('date', '')
                    self._draw_truncated(draw, ds, font_row,
                                         cx + sub_num_w + 3, text_y,
                                         sub_date_w - 6, colore_testo)

                    # -- ORA --
                    ora = ev.get('time', '')
                    self._draw_truncated(draw, ora, font_row,
                                         cx + sub_num_w + sub_date_w + 2, text_y,
                                         sub_ora_w - 4, colore_testo)

                    # -- LOCALITA' --
                    loc = ev.get('location', '').upper()
                    self._draw_truncated(draw, loc, font_row,
                                         cx + sub_num_w + sub_date_w + sub_ora_w + 3, text_y,
                                         sub_loc_w - 6, colore_dim)

                    # -- INDIRIZZO --
                    addr = ev.get('address', '')
                    self._draw_truncated(draw, addr, font_row,
                                         cx + sub_num_w + sub_date_w + sub_ora_w + sub_loc_w + 3,
                                         text_y, sub_addr_w - 6, colore_dim)

                    cy += row_h

                # Bordi verticali colonna
                draw.line([(cx, start_y), (cx, cy)], fill=colore_oro, width=1)
                draw.line([(cx + total_col_w, start_y), (cx + total_col_w, cy)],
                          fill=colore_oro, width=1)
                # Separatori interni verticali
                sep_x_list = [
                    sub_num_w,
                    sub_num_w + sub_date_w,
                    sub_num_w + sub_date_w + sub_ora_w,
                    sub_num_w + sub_date_w + sub_ora_w + sub_loc_w,
                ]
                for sx in sep_x_list:
                    draw.line([(cx + sx, start_y), (cx + sx, cy)],
                              fill=(80, 90, 120, 60), width=1)

            # Footer pagina
            ft = self._get_font(9)
            ft_text = "\u00a9 Comitato Giusto Dire No \u2014 Collezione Completa Eventi \u2014 Coordinamento Liguria e Massa"
            ftb = draw.textbbox((0, 0), ft_text, font=ft)
            draw.text(((self.PAGE_W - (ftb[2] - ftb[0])) // 2, self.PAGE_H - 32),
                      ft_text, fill=(100, 95, 80), font=ft)

            # Salva a 300 DPI
            page_rgb = self._page_to_rgb(page)
            page_rgb = page_rgb.resize((2480, 3508), Image.LANCZOS)
            filename = f"album_summary_{p_idx + 1:02d}.png"
            path = os.path.join(output_dir, filename)
            page_rgb.save(path, "PNG", quality=95)
            summary_paths.append(path)

        return summary_paths

    def _draw_truncated(self, draw, text, font, x, y, max_w, color):
        """Helper: disegna testo troncato con '..' se eccede max_w pixel."""
        if not text:
            return
        if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
            draw.text((x, y), text, fill=color, font=font)
            return
        while text and draw.textbbox((0, 0), text + "..", font=font)[2] > max_w:
            text = text[:-1]
        draw.text((x, y), text + "..", fill=color, font=font)

    # ---------------------------------------------------------------
    #  PAGINE FIGURINE
    # ---------------------------------------------------------------

    def generate_album_pages(self, events, output_dir="output"):
        """
        Genera le pagine dell'album come immagini PNG (A4 portrait).
        Supporta layout verticale (dritto) e obliquo (sfalsato).
        Gli slot senza immagine vengono mostrati come placeholder figurina
        (stile album vuoto) con bordo, numero e effetto rilievo.
        Ritorna la lista dei percorsi delle immagini generate.
        """
        os.makedirs(output_dir, exist_ok=True)

        # Usa TUTTI gli eventi (quelli senza immagine avranno placeholder)
        valid_events = list(events)

        if not valid_events:
            return []

        total_pages = math.ceil(len(valid_events) / self.stickers_per_page)
        
        # Affinché ci siano pagine a coppie destinate all'incollaggio prima del cartone posteriore
        if total_pages % 2 != 0:
            total_pages += 1
            
        generated_pages_full = []
        generated_pages_empty = []

        # Calcolo dimensioni sticker per A4 portrait con N righe x M colonne
        usable_w = self.PAGE_W - self.MARGIN_X * 2
        header_space = 55
        usable_h = self.PAGE_H - self.MARGIN_TOP - self.MARGIN_BOTTOM - header_space
        gap_x = max(10, 30 - self.cols * 4)
        gap_y = max(8, 24 - self.rows * 3)

        # In modalità obliqua, serve un po' di margine extra per lo sfalsamento
        oblique_offset = 20 if self.layout == "obliquo" else 0

        sticker_w = (usable_w - gap_x * (self.cols - 1) - oblique_offset) // self.cols
        sticker_h = (usable_h - gap_y * (self.rows - 1)) // self.rows

        for page_idx in range(total_pages):
            page_full = self._create_page_background()
            draw_full = ImageDraw.Draw(page_full)
            
            page_empty = None
            draw_empty = None
            if self.empty_album_mode:
                page_empty = self._create_page_background()
                draw_empty = ImageDraw.Draw(page_empty)

            # --- Header pagina ---
            font_header = self._get_font(20, bold=True)
            font_sub = self._get_font(12)
            start_num = page_idx * self.stickers_per_page + 1
            end_num = min(start_num + self.stickers_per_page - 1, len(valid_events))

            header_text = "GIUSTO DIRE NO  —  ALBUM EVENTI"
            bbox = draw_full.textbbox((0, 0), header_text, font=font_header)
            header_w = bbox[2] - bbox[0]
            
            draw_full.text(((self.PAGE_W - header_w) // 2, 28), header_text, fill=self.COLOR_HEADER_TEXT, font=font_header)
            if draw_empty:
                draw_empty.text(((self.PAGE_W - header_w) // 2, 28), header_text, fill=self.COLOR_HEADER_TEXT, font=font_header)

            page_label = f"Pagina {page_idx + 1} di {total_pages}  •  Figurine {start_num}–{end_num}"
            bbox2 = draw_full.textbbox((0, 0), page_label, font=font_sub)
            label_w = bbox2[2] - bbox2[0]
            
            draw_full.text(((self.PAGE_W - label_w) // 2, 52), page_label, fill=(160, 150, 120), font=font_sub)
            if draw_empty:
                draw_empty.text(((self.PAGE_W - label_w) // 2, 52), page_label, fill=(160, 150, 120), font=font_sub)

            # --- Posizionamento figurine ---
            start_y = self.MARGIN_TOP

            for slot in range(self.stickers_per_page):
                ev_idx = page_idx * self.stickers_per_page + slot

                row = slot // self.cols
                col = slot % self.cols

                x = self.MARGIN_X + col * (sticker_w + gap_x)
                y = start_y + row * (sticker_h + gap_y)

                # Layout obliquo: righe dispari sfalsate a destra
                if self.layout == "obliquo" and row % 2 == 1:
                    x += oblique_offset

                # Se ci sono slot vuoti alla fine dell'album (ultima pagina), riempi con rettangolini numerati
                if ev_idx >= len(valid_events):
                    sticker_placeholder, _ = self._create_sticker(
                        image_path='',
                        number=ev_idx + 1,
                        location='',
                        date='',
                        sticker_w=sticker_w,
                        sticker_h=sticker_h,
                        empty=True
                    )
                    page_full.paste(sticker_placeholder, (int(x), int(y)), sticker_placeholder)
                    
                    if self.empty_album_mode and page_empty:
                        page_empty.paste(sticker_placeholder, (int(x), int(y)), sticker_placeholder)
                    continue

                ev = valid_events[ev_idx]

                # Controlla se l'evento ha un'immagine valida
                has_valid_image = bool(self._resolve_image_path(ev.get('image_path', '')))

                if has_valid_image:
                    # 1. Genera la figurina piena con l'immagine
                    sticker_full, inner_rect = self._create_sticker(
                        image_path=ev.get('image_path', ''),
                        number=ev_idx + 1,
                        location=ev.get('location', ''),
                        date=ev.get('date', ''),
                        sticker_w=sticker_w,
                        sticker_h=sticker_h,
                        empty=False
                    )
                    ox, oy, dw, dh = inner_rect

                    # 2. Esporta la figurina pura "Stile Effetto Album"
                    if self.export_stickers:
                        bx, by = int(x + ox), int(y + oy)
                        bx2, by2 = bx + dw, by + dh
                        bg_crop = page_full.crop((bx, by, bx2, by2))
                        st_crop = sticker_full.crop((ox, oy, ox + dw, oy + dh))
                        bg_crop.paste(st_crop, (0, 0), st_crop)
                        stickers_dir = os.path.join(output_dir, "stickers")
                        os.makedirs(stickers_dir, exist_ok=True)
                        stk_path = os.path.join(stickers_dir, f"{ev_idx + 1:03d}.png")
                        bg_crop.save(stk_path, "PNG", quality=100)

                    # 3. Incolla lo sticker pieno sulla pagina piena
                    page_full.paste(sticker_full, (int(x), int(y)), sticker_full)
                else:
                    # Slot senza immagine: genera placeholder stile album vuoto
                    # (bordo visibile, numero identificativo, effetto rilievo)
                    sticker_placeholder, _ = self._create_sticker(
                        image_path=ev.get('image_path', ''),
                        number=ev_idx + 1,
                        location=ev.get('location', ''),
                        date=ev.get('date', ''),
                        sticker_w=sticker_w,
                        sticker_h=sticker_h,
                        empty=True
                    )
                    page_full.paste(sticker_placeholder, (int(x), int(y)), sticker_placeholder)

                # 4. Incolla lo sticker vuoto sulla pagina vuota se richiesta
                if self.empty_album_mode and page_empty:
                    sticker_empty, _ = self._create_sticker(
                        image_path=ev.get('image_path', ''),
                        number=ev_idx + 1,
                        location=ev.get('location', ''),
                        date=ev.get('date', ''),
                        sticker_w=sticker_w,
                        sticker_h=sticker_h,
                        empty=True
                    )
                    page_empty.paste(sticker_empty, (int(x), int(y)), sticker_empty)

            # --- Footer pagina ---
            font_footer = self._get_font(9)
            footer_text = "© Comitato Giusto Dire No — Collezione Completa Eventi — Coordinamento Liguria e Massa"
            bbox3 = draw_full.textbbox((0, 0), footer_text, font=font_footer)
            footer_w = bbox3[2] - bbox3[0]
            draw_full.text(((self.PAGE_W - footer_w) // 2, self.PAGE_H - 32), footer_text, fill=(100, 95, 80), font=font_footer)
            if draw_empty:
                draw_empty.text(((self.PAGE_W - footer_w) // 2, self.PAGE_H - 32), footer_text, fill=(100, 95, 80), font=font_footer)

            # Salva pagina(e) a 300 DPI per stampa tipografica
            page_rgb_full = self._page_to_rgb(page_full)
            page_rgb_full = page_rgb_full.resize((2480, 3508), Image.LANCZOS)
            page_path_full = os.path.join(output_dir, f"album_page_{page_idx + 1:03d}.png")
            page_rgb_full.save(page_path_full, "PNG", quality=95)
            generated_pages_full.append(page_path_full)
            
            if self.empty_album_mode and page_empty:
                page_rgb_empty = self._page_to_rgb(page_empty)
                page_rgb_empty = page_rgb_empty.resize((2480, 3508), Image.LANCZOS)
                page_path_empty = os.path.join(output_dir, f"album_page_empty_{page_idx + 1:03d}.png")
                page_rgb_empty.save(page_path_empty, "PNG", quality=95)
                generated_pages_empty.append(page_path_empty)

        return generated_pages_full, generated_pages_empty

    # ---------------------------------------------------------------
    #  GENERAZIONE COMPLETA
    # ---------------------------------------------------------------

    def generate_full_album(self, events, output_dir="output"):
        """
        Genera l'album completo: copertina + pagine figurine + ultima pagina.
        """
        # NON filtrare qui, per permettere i placeholder degli eventi senza immagine
        valid_events = list(events)

        cover_path = self.generate_cover(len(valid_events), output_dir)

        # Se c'è un'immagine custom sulla copertina, non creiamo più la pagina aggiuntiva con le scritte (come richiesto)
        inner_cover_path = None

        guard_front = self.generate_logo_page(output_dir, "album_page_000_guard_f.png", is_front=True)
        pages_full, pages_empty = self.generate_album_pages(valid_events, output_dir)
        
        # Genera pagine riepilogative (Summary) — solo se attivato
        summary_pages = []
        if self.show_summary:
            summary_pages = self.generate_summary_pages(valid_events, output_dir)
        
        guard_back = self.generate_logo_page(output_dir, "album_page_zzz_guard_b.png")
        back_path = self.generate_back_cover(len(valid_events), output_dir)

        # Costruisci la sequenza completa delle pagine
        # Se c'e' inner cover: cover -> inner_cover -> guard -> pagine -> summary -> guard -> back
        # Altrimenti: cover -> guard -> pagine -> summary -> guard -> back
        pre_pages = [cover_path]
        if inner_cover_path:
            pre_pages.append(inner_cover_path)
        pre_pages.append(guard_front)

        # Genera PDF combinato Pieno
        pdf_buffer = None
        all_pages_full = pre_pages + pages_full + summary_pages + [guard_back, back_path]
        try:
            def image_generator(paths):
                for p in paths:
                    with Image.open(p) as img:
                        yield img.convert("RGB")

            pdf_buffer = io.BytesIO()
            first_img = Image.open(all_pages_full[0]).convert("RGB")
            first_img.save(pdf_buffer, "PDF", save_all=True, append_images=image_generator(all_pages_full[1:]), resolution=150.0)
            pdf_buffer.seek(0)
            first_img.close()
        except Exception as e:
            print(f"Errore generazione PDF: {e}")
            pdf_buffer = None

        # Genera PDF combinato Vuoto (se richiesto)
        pdf_empty_buffer = None
        if self.empty_album_mode and pages_empty:
            all_pages_empty = pre_pages + pages_empty + summary_pages + [guard_back, back_path]
            try:
                def image_generator_empty(paths):
                    for p in paths:
                        with Image.open(p) as img:
                            yield img.convert("RGB")

                pdf_empty_buffer = io.BytesIO()
                first_img_e = Image.open(all_pages_empty[0]).convert("RGB")
                first_img_e.save(pdf_empty_buffer, "PDF", save_all=True, append_images=image_generator_empty(all_pages_empty[1:]), resolution=150.0)
                pdf_empty_buffer.seek(0)
                first_img_e.close()
            except Exception as e:
                print(f"Errore generazione PDF vuoto: {e}")
                pdf_empty_buffer = None

        # Aggiungiamo le pagine supplementari alla lista per la preview
        if inner_cover_path:
            pages_full.insert(0, inner_cover_path)
        pages_full.insert(0, guard_front)
        
        # Aggiungiamo il summary alla lista preview
        for s_pg in summary_pages:
            pages_full.append(s_pg)
            
        pages_full.append(guard_back)
        pages_full.append(back_path)

        zip_buffer = None
        if self.export_stickers:
            import zipfile
            stickers_dir = os.path.join(output_dir, "stickers")
            if os.path.exists(stickers_dir):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in os.listdir(stickers_dir):
                        if f.endswith(".png"):
                            zf.write(os.path.join(stickers_dir, f), f)
                zip_buffer.seek(0)

        return cover_path, pages_full, pdf_buffer, pdf_empty_buffer, zip_buffer
