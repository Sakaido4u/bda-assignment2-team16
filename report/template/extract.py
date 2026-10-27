import fitz
d = fitz.open("report/template/format.pdf")
for pno, page in enumerate(d):
    print("page", pno, page.rect)
    for img in page.get_images(full=True):
        x = d.extract_image(img[0]); bbox = page.get_image_bbox(img)
        fn = f"report/template/p{pno}_img{img[0]}.{x['ext']}"
        open(fn, "wb").write(x["image"]); print(fn, x["width"], x["height"], bbox)
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip(): print(f"  {s['font']:28s} {s['size']:5.1f} #{s['color']:06x} {s['text'][:70]}")
    print("  drawings:", [(round(r['rect'].x0),round(r['rect'].y0),round(r['rect'].x1),round(r['rect'].y1)) for r in page.get_drawings()][:6])
