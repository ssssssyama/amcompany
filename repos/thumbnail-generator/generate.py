"""BOOTH用サムネイル自動生成ツール — 620x620pxの商品サムネイルを生成する"""

import argparse
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# デフォルトフォントパス（日本語対応）
DEFAULT_FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
FALLBACK_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

# サムネイルサイズ
WIDTH = 620
HEIGHT = 620

# プリセットカラーテーマ
THEMES = {
    "purple": {"bg1": "#6C5CE7", "bg2": "#341f97", "accent": "#a29bfe", "text": "#FFFFFF"},
    "blue": {"bg1": "#0984e3", "bg2": "#0652DD", "accent": "#74b9ff", "text": "#FFFFFF"},
    "green": {"bg1": "#00b894", "bg2": "#006266", "accent": "#55efc4", "text": "#FFFFFF"},
    "red": {"bg1": "#e17055", "bg2": "#c0392b", "accent": "#fab1a0", "text": "#FFFFFF"},
    "pink": {"bg1": "#e84393", "bg2": "#B53471", "accent": "#fd79a8", "text": "#FFFFFF"},
    "orange": {"bg1": "#e17055", "bg2": "#d35400", "accent": "#ffeaa7", "text": "#FFFFFF"},
    "dark": {"bg1": "#2d3436", "bg2": "#0d0d0d", "accent": "#636e72", "text": "#FFFFFF"},
    "gold": {"bg1": "#f9ca24", "bg2": "#f0932b", "accent": "#fff200", "text": "#2d3436"},
}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """HEXカラーコードをRGBタプルに変換する"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def create_gradient(width: int, height: int, color1: str, color2: str) -> Image.Image:
    """対角グラデーション背景を生成する"""
    img = Image.new("RGB", (width, height))
    r1, g1, b1 = hex_to_rgb(color1)
    r2, g2, b2 = hex_to_rgb(color2)

    for y in range(height):
        for x in range(width):
            # 対角線方向のグラデーション
            ratio = (x + y) / (width + height)
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            img.putpixel((x, y), (r, g, b))

    return img


def draw_decorative_circles(draw: ImageDraw.ImageDraw, width: int, height: int, accent_color: str, count: int = 8):
    """装飾用の半透明円を描画する"""
    import random
    rng = random.Random(42)  # 固定シードで再現性確保
    accent_rgb = hex_to_rgb(accent_color)

    for _ in range(count):
        x = rng.randint(-50, width + 50)
        y = rng.randint(-50, height + 50)
        radius = rng.randint(20, 120)
        alpha = rng.randint(15, 50)
        color = (*accent_rgb, alpha)
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=color,
        )


def draw_corner_decorations(draw: ImageDraw.ImageDraw, width: int, height: int, accent_color: str):
    """角の装飾線を描画する"""
    accent_rgb = hex_to_rgb(accent_color)
    color = (*accent_rgb, 100)
    line_len = 60
    margin = 30
    line_width = 3

    # 左上
    draw.line([(margin, margin), (margin + line_len, margin)], fill=color, width=line_width)
    draw.line([(margin, margin), (margin, margin + line_len)], fill=color, width=line_width)
    # 右上
    draw.line([(width - margin, margin), (width - margin - line_len, margin)], fill=color, width=line_width)
    draw.line([(width - margin, margin), (width - margin, margin + line_len)], fill=color, width=line_width)
    # 左下
    draw.line([(margin, height - margin), (margin + line_len, height - margin)], fill=color, width=line_width)
    draw.line([(margin, height - margin), (margin, height - margin - line_len)], fill=color, width=line_width)
    # 右下
    draw.line([(width - margin, height - margin), (width - margin - line_len, height - margin)], fill=color, width=line_width)
    draw.line([(width - margin, height - margin), (width - margin, height - margin - line_len)], fill=color, width=line_width)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """日本語フォントを読み込む"""
    for path in [DEFAULT_FONT_PATH, FALLBACK_FONT_PATH]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_thumbnail(
    title: str,
    subtitle: str = "",
    theme: str = "purple",
    icon: str = "🎮",
    brand: str = "VRC Tools",
    output: str = "thumbnail.png",
):
    """BOOTHサムネイル画像を生成する"""
    colors = THEMES.get(theme, THEMES["purple"])

    # 背景グラデーション
    img = create_gradient(WIDTH, HEIGHT, colors["bg1"], colors["bg2"])

    # RGBA変換して半透明要素を描画
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # 装飾円
    draw_decorative_circles(overlay_draw, WIDTH, HEIGHT, colors["accent"])
    img = Image.alpha_composite(img, overlay)

    # 角の装飾
    corner_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    corner_draw = ImageDraw.Draw(corner_overlay)
    draw_corner_decorations(corner_draw, WIDTH, HEIGHT, colors["accent"])
    img = Image.alpha_composite(img, corner_overlay)

    draw = ImageDraw.Draw(img)

    # アイコン（絵文字）
    icon_font = load_font(80)
    icon_bbox = draw.textbbox((0, 0), icon, font=icon_font)
    icon_w = icon_bbox[2] - icon_bbox[0]
    draw.text(((WIDTH - icon_w) // 2, 140), icon, font=icon_font, fill=colors["text"])

    # タイトル
    title_font = load_font(48)
    # タイトルが長い場合は自動で小さくする
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    if title_w > WIDTH - 80:
        title_font = load_font(36)
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]

    draw.text(
        ((WIDTH - title_w) // 2, 260),
        title,
        font=title_font,
        fill=colors["text"],
    )

    # 区切り線
    line_y = 330
    accent_rgb = hex_to_rgb(colors["accent"])
    draw.line(
        [(WIDTH // 2 - 80, line_y), (WIDTH // 2 + 80, line_y)],
        fill=(*accent_rgb, 180),
        width=2,
    )

    # サブタイトル
    if subtitle:
        sub_font = load_font(24)
        sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(
            ((WIDTH - sub_w) // 2, 355),
            subtitle,
            font=sub_font,
            fill=(*hex_to_rgb(colors["text"]), 200),
        )

    # ブランド名（下部）
    brand_font = load_font(18)
    brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
    brand_w = brand_bbox[2] - brand_bbox[0]
    draw.text(
        ((WIDTH - brand_w) // 2, HEIGHT - 70),
        brand,
        font=brand_font,
        fill=(*hex_to_rgb(colors["text"]), 150),
    )

    # 「VRChat」タグ
    tag_font = load_font(14)
    tag_text = "for VRChat"
    tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    draw.text(
        ((WIDTH - tag_w) // 2, HEIGHT - 45),
        tag_text,
        font=tag_font,
        fill=(*hex_to_rgb(colors["text"]), 120),
    )

    # 価格バッジ（右上）— オプション
    # draw_price_badge(draw, "¥200", colors)

    # RGB変換して保存
    img = img.convert("RGB")
    img.save(output, "PNG", quality=95)
    print(f"✅ サムネイル生成完了: {output}")
    print(f"   サイズ: {WIDTH}x{HEIGHT}px")


def generate_all_products():
    """全商品のサムネイルを一括生成する"""
    products = [
        {
            "title": "Chatbox デコレーター",
            "subtitle": "チャットを華やかに装飾",
            "theme": "purple",
            "icon": "✨",
            "output": "thumbnail_chatbox_decorator.png",
        },
        {
            "title": "今日の運勢おみくじBot",
            "subtitle": "毎日の運勢をChatboxに表示",
            "theme": "gold",
            "icon": "⛩️",
            "output": "thumbnail_omikuji.png",
        },
        {
            "title": "OSCタイマー",
            "subtitle": "カウントダウン＆ポモドーロ",
            "theme": "blue",
            "icon": "⏱️",
            "output": "thumbnail_timer.png",
        },
    ]

    for product in products:
        generate_thumbnail(**product)


def main():
    parser = argparse.ArgumentParser(description="BOOTH用サムネイル自動生成ツール")
    parser.add_argument("--title", type=str, help="商品タイトル")
    parser.add_argument("--subtitle", type=str, default="", help="サブタイトル/キャッチコピー")
    parser.add_argument("--theme", choices=list(THEMES.keys()), default="purple", help="カラーテーマ")
    parser.add_argument("--icon", type=str, default="🎮", help="アイコン（絵文字）")
    parser.add_argument("--brand", type=str, default="VRC Tools", help="ブランド名")
    parser.add_argument("--output", type=str, default="thumbnail.png", help="出力ファイル名")
    parser.add_argument("--all", action="store_true", help="全商品のサムネイルを一括生成")
    args = parser.parse_args()

    if args.all:
        generate_all_products()
    elif args.title:
        generate_thumbnail(
            title=args.title,
            subtitle=args.subtitle,
            theme=args.theme,
            icon=args.icon,
            brand=args.brand,
            output=args.output,
        )
    else:
        parser.print_help()
        print("\n使用例:")
        print('  python generate.py --title "Chatbox デコレーター" --theme purple --icon "✨"')
        print("  python generate.py --all  # 全商品一括生成")


if __name__ == "__main__":
    main()
