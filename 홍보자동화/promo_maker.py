# 자료 폴더의 사진들을 인스타그램용 1080x1080 정사각형으로 변환하고,
# 가게정보.txt를 읽어 홍보 문구까지 함께 만들어서 완성 폴더에 저장합니다.
import datetime
import re
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "자료"
OUTPUT_DIR = BASE_DIR / "완성"
TARGET_SIZE = 1080

LOGO_WIDTH_RATIO = 0.15   # 로고 가로 크기: 사진 가로 폭의 15%
LOGO_MARGIN = 40          # 로고와 사진 가장자리 사이 여백(픽셀)
LOGO_OPACITY = 0.9        # 로고 투명도 (1.0이면 완전 불투명)
LOGO_BG_PADDING = 16      # 로고 뒤 흰색 배경이 로고보다 여유를 두는 두께(픽셀)


def find_logo_file() -> Path | None:
    # '로고.jpg' 또는 '로고.png'를 홍보자동화 폴더와 자료 폴더에서 찾는다.
    for folder in (BASE_DIR, SOURCE_DIR):
        for name in ("로고.jpg", "로고.jpeg", "로고.png"):
            candidate = folder / name
            if candidate.exists():
                return candidate
    return None


def to_square(image: Image.Image, size: int) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size

    # 짧은 변에 맞춰 비율대로 키운 뒤, 가운데 기준으로 긴 변을 잘라낸다.
    scale = size / min(width, height)
    new_width = round(width * scale)
    new_height = round(height * scale)
    image = image.resize((new_width, new_height), Image.LANCZOS)

    left = (new_width - size) // 2
    top = (new_height - size) // 2
    return image.crop((left, top, left + size, top + size))


def add_logo(image: Image.Image, logo_path: Path) -> Image.Image:
    base = image.convert("RGBA")

    with Image.open(logo_path) as logo_img:
        logo = logo_img.convert("RGBA")

    logo_width = round(base.width * LOGO_WIDTH_RATIO)
    logo_height = round(logo.height * (logo_width / logo.width))
    logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

    # 투명도를 적용한다 (알파 채널에 비율을 곱함).
    alpha = logo.split()[3].point(lambda a: int(a * LOGO_OPACITY))
    logo.putalpha(alpha)

    x = base.width - logo_width - LOGO_MARGIN
    y = base.height - logo_height - LOGO_MARGIN

    # 로고가 사진 배경색에 묻히지 않도록 흰색 사각형을 먼저 깔아준다.
    box = (
        x - LOGO_BG_PADDING,
        y - LOGO_BG_PADDING,
        x + logo_width + LOGO_BG_PADDING,
        y + logo_height + LOGO_BG_PADDING,
    )
    white_bg = Image.new("RGBA", base.size, (0, 0, 0, 0))
    white_bg.paste((255, 255, 255, 255), box)
    base.alpha_composite(white_bg)

    base.paste(logo, (x, y), logo)

    return base.convert("RGB")


def find_store_info_file() -> Path | None:
    # '가게 정보.txt' 또는 '가게정보.txt'를 홍보자동화 폴더와 자료 폴더에서 찾는다.
    for folder in (SOURCE_DIR, BASE_DIR):
        for name in ("가게 정보.txt", "가게정보.txt"):
            candidate = folder / name
            if candidate.exists():
                return candidate
    return None


def parse_store_info(path: Path) -> dict:
    fields: dict = {}
    promo_items: list[str] = []
    in_promo = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("-") and in_promo:
            promo_items.append(line.lstrip("- ").strip())
            continue

        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            in_promo = key.startswith("이번 주 홍보할 것")
            if not in_promo:
                fields[key] = value

    fields["promo_items"] = promo_items
    return fields


def clean_sentence_ending(text: str) -> str:
    # 메모체로 적힌 문장을 사장님 말투(합쇼체, ~습니다)에 맞게 다듬는다.
    replacements = {
        "넣음": "넣었습니다",
        "않음": "않습니다",
        "좋음": "좋습니다",
        "많음": "많습니다",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def split_into_sentences(desc: str) -> list[str]:
    # 쉼표로 나열된 설명을 사장님처럼 짧은 문장 여러 개로 나눈다.
    parts = [p.strip() for p in desc.split(",") if p.strip()]
    sentences = []
    for part in parts:
        part = clean_sentence_ending(part)
        if not part.endswith("."):
            part += "."
        sentences.append(part)
    return sentences


def parse_promo_item(raw: str) -> dict:
    name_match = re.search(r"['‘]([^'’]+)['’]", raw)
    price_match = re.search(r"[\d,]+원", raw)

    menu_name = name_match.group(1) if name_match else None
    price = price_match.group(0) if price_match else None

    desc = raw
    if name_match:
        desc = desc.replace(name_match.group(0), "")
    if price_match:
        desc = desc.replace(price_match.group(0), "")
    desc = desc.replace("신메뉴", "")
    desc = re.sub(r"^[,\s]+|[,\s]+$", "", desc)
    desc = re.sub(r",\s*,", ",", desc)

    return {"raw": raw, "menu_name": menu_name, "price": price, "desc": desc}


def pick_josa(word: str, with_final: str, without_final: str) -> str:
    # 받침 유무에 따라 '을/를', '이/가' 같은 조사를 자동으로 고른다.
    if not word:
        return without_final
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0:
        return with_final
    return without_final


def build_hashtags(store_name: str, location: str, menu_names: list[str]) -> list[str]:
    location_parts = [p for p in re.split(r"\s+", location) if p]
    business_type = "카페"

    tags: list[str] = []

    def add(tag: str):
        tag = tag.replace(" ", "")
        if tag and tag not in tags:
            tags.append(tag)

    for part in location_parts[:3]:
        add(f"#{part}{business_type}")
    if location_parts:
        add(f"#{location_parts[0]}맛집")
    add(f"#{store_name}")
    for menu in menu_names:
        add(f"#{menu}")
    add(f"#{business_type}추천")
    add(f"#{business_type}스타그램")
    add("#오늘의카페")
    add("#데일리카페")
    add("#로스터리카페")

    return tags[:10]


def generate_promo_text(store_info_path: Path) -> str:
    info = parse_store_info(store_info_path)

    store_name = info.get("가게 이름", "우리 가게")
    location = info.get("위치", "")
    features = info.get("가게 특징", "")
    customers = info.get("주 고객층", "")
    promo_raw_items = info.get("promo_items", [])

    promos = [parse_promo_item(item) for item in promo_raw_items]
    main_promo = promos[0] if len(promos) > 0 else None
    sub_promo = promos[1] if len(promos) > 1 else None

    menu_name = main_promo["menu_name"] if main_promo and main_promo["menu_name"] else "신메뉴"
    menu_price = f" {main_promo['price']}" if main_promo and main_promo["price"] else ""
    menu_full = f"{menu_name}{menu_price}"
    eul_reul = pick_josa(menu_full, "을", "를")
    i_ga = pick_josa(menu_full, "이", "가")

    desc_sentences = split_into_sentences(main_promo["desc"]) if main_promo else [clean_sentence_ending(features) + "."]
    desc_line = " ".join(desc_sentences)
    desc_block = "\n".join(desc_sentences)

    # 할인/추가 소식 문장도 사장님처럼 담백한 '~습니다'체로 맞춘다.
    sub_text = sub_promo["raw"] if sub_promo else ""
    if sub_text.endswith("할인"):
        sub_text += "해 드립니다."
    elif sub_text and not sub_text.endswith((".", "다")):
        sub_text += "."
    elif sub_text and not sub_text.endswith("."):
        sub_text += "."

    menu_names_for_tags = [m["menu_name"] for m in promos if m["menu_name"]]
    hashtags = build_hashtags(store_name, location, menu_names_for_tags)
    hashtag_line = " ".join(hashtags)

    # 이모지 없이, 짧은 문장을 줄바꿔 쓰는 사장님 말투를 그대로 따른다.
    # 인스타그램용: 짧게, 해시태그만 유지
    texts_instagram = {
        "감성형": (
            f"요즘 날씨가 제법 선선해졌습니다.\n"
            f"{menu_full}{eul_reul} 새로 준비했습니다.\n"
            f"{desc_block}"
        ),
        "정보형": (
            f"{store_name} 이번 주 소식입니다.\n"
            f"{menu_full}{eul_reul} 새로 내놓았습니다.\n"
            f"{desc_line}\n"
            + (f"{sub_text}\n" if sub_text else "")
            + f"위치는 {location}입니다."
        ),
        "이벤트형": (
            f"이번 주 {store_name} 소식입니다.\n"
            + (f"{sub_text}\n" if sub_text else "")
            + f"{menu_full}{i_ga} 함께 나왔습니다.\n"
            f"편하게 들러 주시기 바랍니다."
        ),
    }

    # 네이버 블로그용: 300자 내외로 풀어서, 해시태그 없이
    texts_blog = {
        "감성형": (
            f"{store_name}는 {location}에 자리한 작은 카페입니다.\n"
            f"{clean_sentence_ending(features)}.\n\n"
            f"요즘 아침저녁으로 선선해졌습니다.\n"
            f"이번 주부터 {menu_full}{eul_reul} 새로 준비했습니다.\n"
            f"{desc_block}\n\n"
            + (f"{sub_text}\n\n" if sub_text else "")
            + f"{customers}분들이 자주 찾아 주시는 곳입니다.\n"
            f"조용히 앉아 쉬어가실 수 있도록 자리를 준비해 두었습니다.\n"
            f"지나시는 길에 편하게 들러 주시기 바랍니다."
        ),
        "정보형": (
            f"{store_name} 이번 주 소식을 전해 드립니다.\n\n"
            f"위치는 {location}입니다.\n"
            f"{clean_sentence_ending(features)}.\n\n"
            f"이번 주 새 메뉴로 {menu_full}{i_ga} 나왔습니다.\n"
            f"{desc_block}\n"
            + (f"또한 {sub_text}\n\n" if sub_text else "\n")
            + f"{customers}분들이 편하게 머물다 가실 수 있는 공간입니다.\n"
            f"근처를 지나신다면 한 번 들러 주시기 바랍니다."
        ),
        "이벤트형": (
            f"안녕하세요, {store_name}입니다.\n\n"
            f"이번 주 소식을 전해 드립니다.\n"
            + (f"{sub_text}\n" if sub_text else "")
            + f"더불어 {menu_full}{i_ga} 함께 나왔습니다.\n"
            f"{desc_block}\n\n"
            f"{clean_sentence_ending(features)}.\n"
            f"{customers}분들께 특히 어울리는 공간입니다.\n"
            f"이번 주 안에 편한 시간에 들러 보시기 바랍니다."
        ),
    }

    # 카카오톡 단골 공지용: 존댓말로 3줄 이내, 아주 짧게
    texts_kakao = {
        "감성형": (
            f"안녕하세요, {store_name}입니다.\n"
            f"선선한 날씨에 어울리는 {menu_full}{eul_reul} 준비했습니다.\n"
            f"편하게 들러 주시기 바랍니다."
        ),
        "정보형": (
            f"{store_name} 소식입니다.\n"
            f"{menu_full}{i_ga} 새로 나왔습니다."
            + (f" {sub_text}\n" if sub_text else "\n")
            + f"이번 주 안에 확인해 보시기 바랍니다."
        ),
        "이벤트형": (
            f"{store_name} 이번 주 안내입니다.\n"
            + (f"{sub_text}\n" if sub_text else "")
            + f"{menu_full}{i_ga} 함께 준비되어 있습니다."
        ),
    }

    sections = []
    channels = (
        ("인스타그램용", texts_instagram, True),
        ("네이버 블로그용", texts_blog, False),
        ("카카오톡 단골 공지용", texts_kakao, False),
    )
    for channel, texts, use_hashtags in channels:
        sections.append(f"[{channel}]\n")
        for tone, text in texts.items():
            sections.append(f"▶ {tone} ({len(text)}자)\n{text}\n")
            if use_hashtags:
                sections.append(f"\n{hashtag_line}\n")
            sections.append("\n")
        sections.append("=" * 40 + "\n\n")

    header = f"{store_name} 홍보 문구 ({datetime.date.today().strftime('%Y-%m-%d')} 기준)\n" + "=" * 40 + "\n\n"
    return header + "".join(sections)


def main():
    SOURCE_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    logo_path = find_logo_file()
    if logo_path:
        print(f"로고 파일 발견: {logo_path.name} (사진마다 삽입합니다)")
    else:
        print("로고 파일이 없어서 로고 삽입 없이 진행합니다.")

    image_files = sorted(
        f for f in SOURCE_DIR.iterdir()
        if f.suffix.lower() in (".jpg", ".jpeg", ".png")
        and (logo_path is None or f.resolve() != logo_path.resolve())
    )

    if not image_files:
        print(f"'{SOURCE_DIR.name}' 폴더에 처리할 사진이 없습니다.")
        return

    today = datetime.date.today().strftime("%Y%m%d")

    for index, file_path in enumerate(image_files, start=1):
        with Image.open(file_path) as img:
            squared = to_square(img, TARGET_SIZE)

        if logo_path:
            squared = add_logo(squared, logo_path)

        output_name = f"{today}_{index:02d}.jpg"
        squared.save(OUTPUT_DIR / output_name, "JPEG", quality=95)
        print(f"완료: {file_path.name} -> {output_name}")

    print(f"\n총 {len(image_files)}장 변환 완료! '{OUTPUT_DIR.name}' 폴더를 확인하세요.")

    store_info_path = find_store_info_file()
    if store_info_path:
        promo_text = generate_promo_text(store_info_path)
        promo_output_path = OUTPUT_DIR / "홍보문구.txt"
        promo_output_path.write_text(promo_text, encoding="utf-8")
        print(f"홍보 문구 생성 완료! -> {promo_output_path.name}")
    else:
        print("'가게 정보.txt' 파일을 찾지 못해 홍보 문구 생성은 건너뜁니다.")


if __name__ == "__main__":
    main()
