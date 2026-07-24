from PIL import Image

# Open your source image (must be square for best results)
source_image = "main.png"

sizes = [16, 48, 128]

for size in sizes:
    with Image.open(source_image) as img:
        resized_img = img.resize((size, size), Image.Resampling.LANCZOS)
        resized_img.save(f"icon{size}.png")

print("Icons generated successfully!")