import json
import os

with open('data.json', 'r', encoding='utf-8') as f:
    events = json.load(f)

modified = False
for ev in events:
    # Fix image_path
    img_path = ev.get('image_path', '')
    if img_path and img_path.lower().endswith('.png'):
        alt_jpg = img_path[:-4] + '.jpg'
        if not os.path.exists(img_path) and os.path.exists(alt_jpg):
            ev['image_path'] = alt_jpg
            modified = True

    # Fix sticker_image_path
    stk_path = ev.get('sticker_image_path', '')
    if stk_path and stk_path.lower().endswith('.png'):
        alt_jpg = stk_path[:-4] + '.jpg'
        if not os.path.exists(stk_path) and os.path.exists(alt_jpg):
            ev['sticker_image_path'] = alt_jpg
            modified = True

if modified:
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print("data.json bonificato: corretti riferimenti PNG -> JPG mancanti.")
else:
    print("Nessuna modifica necessaria a data.json.")
