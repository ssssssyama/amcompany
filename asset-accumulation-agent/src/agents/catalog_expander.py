"""CatalogExpanderAgent - カタログ複利型バリエーション生成エージェント

既存ツールからテーマ別バリエーションを自動生成し、カタログを拡大する。
商品数が増えるほど各商品の発見確率が上がるロングテール戦略を実現する。

CPU専用 — GPU不要で24時間蓄積可能。

生成物:
  - Chatboxデコレーター用フレームセット（テーマ別）
  - おみくじBot用占いデータ（テーマ別）
  - 足音パック用プロンプト定義（テーマ別）
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Any

from ..agent import Asset, BaseAgent, Context

logger = logging.getLogger(__name__)

# === フレームセット定義 ===

FRAME_THEMES = {
    "seasonal_spring": {
        "name_ja": "春の桜セット",
        "name_en": "Spring Sakura Set",
        "frames": {
            "sakura": ("🌸 ", " 🌸"),
            "sakura_wind": ("🌸✿ ", " ✿🌸"),
            "butterfly": ("🦋 ", " 🦋"),
            "cherry": ("❀ ", " ❀"),
            "petal": ("⚘ ", " ⚘"),
        },
    },
    "seasonal_summer": {
        "name_ja": "夏の花火セット",
        "name_en": "Summer Fireworks Set",
        "frames": {
            "hanabi": ("🎆✧ ", " ✧🎆"),
            "sparkler": ("🎇 ", " 🎇"),
            "sun": ("☀️ ", " ☀️"),
            "wave": ("🌊 ", " 🌊"),
            "palm": ("🌴 ", " 🌴"),
        },
    },
    "seasonal_autumn": {
        "name_ja": "秋の紅葉セット",
        "name_en": "Autumn Leaves Set",
        "frames": {
            "momiji": ("🍁 ", " 🍁"),
            "chestnut": ("🌰 ", " 🌰"),
            "moon": ("🌙 ", " 🌙"),
            "mushroom": ("🍄 ", " 🍄"),
            "harvest": ("🎑 ", " 🎑"),
        },
    },
    "seasonal_winter": {
        "name_ja": "冬の雪セット",
        "name_en": "Winter Snow Set",
        "frames": {
            "yuki": ("❄️ ", " ❄️"),
            "snowman": ("⛄ ", " ⛄"),
            "crystal": ("✻ ", " ✻"),
            "mittens": ("🧤 ", " 🧤"),
            "cocoa": ("☕ ", " ☕"),
        },
    },
    "horror": {
        "name_ja": "ホラーセット",
        "name_en": "Horror Set",
        "frames": {
            "skull": ("💀 ", " 💀"),
            "ghost": ("👻 ", " 👻"),
            "bat": ("🦇 ", " 🦇"),
            "spider": ("🕷️ ", " 🕷️"),
            "blood": ("🩸 ", " 🩸"),
        },
    },
    "rpg": {
        "name_ja": "RPG冒険者セット",
        "name_en": "RPG Adventurer Set",
        "frames": {
            "sword": ("⚔️ ", " ⚔️"),
            "shield": ("🛡️ ", " 🛡️"),
            "potion": ("🧪 ", " 🧪"),
            "scroll": ("📜 ", " 📜"),
            "gem": ("💎 ", " 💎"),
        },
    },
    "kaomoji": {
        "name_ja": "顔文字セット",
        "name_en": "Kaomoji Set",
        "frames": {
            "happy": ("(╹◡╹) ", " (╹◡╹)"),
            "excited": ("(ﾉ◕ヮ◕)ﾉ ", " ヽ(◕ヮ◕ヽ)"),
            "shy": ("(//ω//) ", " (//ω//)"),
            "cool": ("( •̀ω•́ )σ ", " σ( •̀ω•́ )"),
            "sleepy": ("(｡-ω-)zzZ ", " Zzz(-ω-｡)"),
        },
    },
    "retro_game": {
        "name_ja": "レトロゲームセット",
        "name_en": "Retro Game Set",
        "frames": {
            "pixel_heart": ("♥ ▶ ", " ◀ ♥"),
            "coin": ("🪙 ", " 🪙"),
            "joystick": ("🕹️ ", " 🕹️"),
            "level_up": ("⬆️ LV. ", " .LV ⬆️"),
            "game_over": ("☠ GAME ", " OVER ☠"),
        },
    },
}

# === おみくじデータ定義 ===

FORTUNE_THEMES = {
    "halloween": {
        "name_ja": "ハロウィン占い",
        "name_en": "Halloween Fortune",
        "fortunes": [
            {"rank": "大吉", "emoji": "🎃", "weight": 10},
            {"rank": "吉", "emoji": "👻", "weight": 20},
            {"rank": "中吉", "emoji": "🕸️", "weight": 25},
            {"rank": "小吉", "emoji": "🦇", "weight": 20},
            {"rank": "末吉", "emoji": "🕯️", "weight": 15},
            {"rank": "凶", "emoji": "💀", "weight": 8},
            {"rank": "大凶", "emoji": "☠️", "weight": 2},
        ],
        "lucky_items": [
            "かぼちゃランタン", "魔女の帽子", "黒猫のマスコット", "コウモリの羽",
            "蜘蛛の巣アクセ", "骸骨ネックレス", "ゴーストマント", "月夜のペンダント",
            "キャンドル", "毒リンゴ", "魔法の杖", "呪文書",
        ],
        "advice": [
            "仮装を変えると運気が上がる",
            "今日は怖いワールドで肝試し",
            "お菓子を配ると友達が増える",
            "暗い場所で新しい出会いが",
        ],
    },
    "valentine": {
        "name_ja": "バレンタイン占い",
        "name_en": "Valentine Fortune",
        "fortunes": [
            {"rank": "大吉", "emoji": "💖", "weight": 10},
            {"rank": "吉", "emoji": "💝", "weight": 20},
            {"rank": "中吉", "emoji": "💕", "weight": 25},
            {"rank": "小吉", "emoji": "💗", "weight": 20},
            {"rank": "末吉", "emoji": "💛", "weight": 15},
            {"rank": "凶", "emoji": "💔", "weight": 8},
            {"rank": "大凶", "emoji": "🖤", "weight": 2},
        ],
        "lucky_items": [
            "チョコレート", "ハートのアクセ", "赤いリボン", "手紙",
            "ぬいぐるみ", "花束", "指輪", "ケーキ",
            "キャンドル", "ペアマグカップ", "オルゴール", "フォトフレーム",
        ],
        "advice": [
            "今日は思い切って話しかけてみよう",
            "甘いものを食べると恋愛運UP",
            "ピンクのアクセサリーが吉",
            "フレンドと一緒にミラーワールドへ",
        ],
    },
    "christmas": {
        "name_ja": "クリスマス占い",
        "name_en": "Christmas Fortune",
        "fortunes": [
            {"rank": "大吉", "emoji": "🎄", "weight": 10},
            {"rank": "吉", "emoji": "🎅", "weight": 20},
            {"rank": "中吉", "emoji": "🎁", "weight": 25},
            {"rank": "小吉", "emoji": "⭐", "weight": 20},
            {"rank": "末吉", "emoji": "🔔", "weight": 15},
            {"rank": "凶", "emoji": "🧦", "weight": 8},
            {"rank": "大凶", "emoji": "🪨", "weight": 2},
        ],
        "lucky_items": [
            "クリスマスツリー", "トナカイの角", "サンタ帽", "雪の結晶アクセ",
            "ジンジャークッキー", "暖炉", "ホットココア", "そり",
            "キャンドル", "リース", "ベル", "スノードーム",
        ],
        "advice": [
            "プレゼント交換で運気UP",
            "雪のワールドでクリスマス気分を",
            "今日は赤と緑のコーデで",
            "フレンドにメッセージを送ろう",
        ],
    },
    "newyear": {
        "name_ja": "お正月占い",
        "name_en": "New Year Fortune",
        "fortunes": [
            {"rank": "大吉", "emoji": "🎍", "weight": 10},
            {"rank": "吉", "emoji": "🌅", "weight": 20},
            {"rank": "中吉", "emoji": "🎌", "weight": 25},
            {"rank": "小吉", "emoji": "🧧", "weight": 20},
            {"rank": "末吉", "emoji": "🎐", "weight": 15},
            {"rank": "凶", "emoji": "👹", "weight": 8},
            {"rank": "大凶", "emoji": "😱", "weight": 2},
        ],
        "lucky_items": [
            "お年玉袋", "破魔矢", "獅子舞マスコット", "お雑煮",
            "おせち", "書き初め", "凧", "羽子板",
            "干支のマスコット", "鏡餅", "初日の出写真", "達磨",
        ],
        "advice": [
            "初詣ワールドで運気を上げよう",
            "和風アバターに着替えると吉",
            "今年の目標を設定すると道が開ける",
            "新しいフレンドを作ると発展運UP",
        ],
    },
    "gaming": {
        "name_ja": "ゲーマー占い",
        "name_en": "Gamer Fortune",
        "fortunes": [
            {"rank": "大吉", "emoji": "🏆", "weight": 10},
            {"rank": "吉", "emoji": "🎮", "weight": 20},
            {"rank": "中吉", "emoji": "🕹️", "weight": 25},
            {"rank": "小吉", "emoji": "🎯", "weight": 20},
            {"rank": "末吉", "emoji": "🎲", "weight": 15},
            {"rank": "凶", "emoji": "💣", "weight": 8},
            {"rank": "大凶", "emoji": "💥", "weight": 2},
        ],
        "lucky_items": [
            "ゲーミングヘッドセット", "レアドロップ", "経験値ブースト", "コントローラー",
            "エナジードリンク", "攻略本", "セーブポイント", "ボーナスステージ",
            "コンボ", "必殺技", "隠しコマンド", "チートコード",
        ],
        "advice": [
            "今日はゲームワールドで遊ぶと吉",
            "新しいゲームに挑戦すると運気UP",
            "マルチプレイで協力すると大吉",
            "休憩も大事！たまにはまったりワールドへ",
        ],
    },
}

# === 足音プロンプト拡張 ===

FOOTSTEP_EXPANSION_THEMES = {
    "horror": {
        "name_ja": "ホラー足音拡張",
        "prompts": {
            "creaky_wood": "single creepy footstep on old creaky wooden floor, horror, dark, close-up, foley",
            "dungeon_stone": "single echoing footstep in dark dungeon, stone floor, horror, reverb, foley",
            "swamp": "single footstep in dark swamp, squelching, horror, close-up, foley",
            "broken_glass": "single footstep on broken glass, horror, crunching, close-up, foley",
            "bone": "single footstep on pile of bones, horror, rattling, close-up, foley",
        },
    },
    "scifi": {
        "name_ja": "SF足音拡張",
        "prompts": {
            "spaceship_floor": "single footstep on spaceship metal floor, sci-fi, electronic hum, close-up, foley",
            "alien_ground": "single footstep on alien planet surface, sci-fi, strange texture, close-up, foley",
            "energy_bridge": "single footstep on energy bridge, sci-fi, buzzing, close-up, foley",
            "zero_gravity": "single magnetic boot step in zero gravity, sci-fi, click, close-up, foley",
            "cyborg": "single mechanical footstep, cybernetic, servo motor, sci-fi, close-up, foley",
        },
    },
    "fantasy": {
        "name_ja": "ファンタジー足音拡張",
        "prompts": {
            "crystal_cave": "single footstep in crystal cave, fantasy, resonant chime, close-up, foley",
            "cloud_walk": "single soft footstep on clouds, fantasy, ethereal, close-up, foley",
            "enchanted_forest": "single footstep on enchanted forest floor, magical sparkle, close-up, foley",
            "dragon_scale": "single footstep on dragon scales, fantasy, metallic, close-up, foley",
            "marble_temple": "single footstep in marble temple, fantasy, grand echo, close-up, foley",
        },
    },
}


class CatalogExpanderAgent(BaseAgent):
    name = "catalog_expander"
    description = "カタログ複利型バリエーション生成（CPU専用）"
    interval_seconds = 1800
    requires = []
    monetization = "direct_sale"

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.max_per_cycle = self.params.get("max_per_cycle", 5)

    def _find_missing_frame_themes(self, catalog: Any) -> list[str]:
        """まだ生成していないフレームテーマを見つける。"""
        missing = []
        for theme_id in FRAME_THEMES:
            count = catalog.count(
                agent=self.name, product_type="frame_pack", theme=theme_id
            )
            if count == 0:
                missing.append(theme_id)
        return missing

    def _find_missing_fortune_themes(self, catalog: Any) -> list[str]:
        """まだ生成していないおみくじテーマを見つける。"""
        missing = []
        for theme_id in FORTUNE_THEMES:
            count = catalog.count(
                agent=self.name, product_type="fortune_pack", theme=theme_id
            )
            if count == 0:
                missing.append(theme_id)
        return missing

    def _find_missing_footstep_themes(self, catalog: Any) -> list[str]:
        """まだ生成していない足音拡張テーマを見つける。"""
        missing = []
        for theme_id in FOOTSTEP_EXPANSION_THEMES:
            count = catalog.count(
                agent=self.name, product_type="footstep_prompts", theme=theme_id
            )
            if count == 0:
                missing.append(theme_id)
        return missing

    def _generate_frame_pack(
        self, theme_id: str, output_dir: Path
    ) -> Asset | None:
        """フレームパックを生成する。"""
        theme = FRAME_THEMES[theme_id]
        pack_dir = output_dir / "frame_packs" / theme_id
        pack_dir.mkdir(parents=True, exist_ok=True)

        # フレーム定義ファイル
        frames_data = {
            "theme_id": theme_id,
            "name_ja": theme["name_ja"],
            "name_en": theme["name_en"],
            "frames": {k: {"prefix": v[0], "suffix": v[1]} for k, v in theme["frames"].items()},
        }
        frames_path = pack_dir / "frames.json"
        with open(frames_path, "w", encoding="utf-8") as f:
            json.dump(frames_data, f, ensure_ascii=False, indent=2)

        # プレビューサンプル
        preview_lines = [f"# {theme['name_ja']} / {theme['name_en']}", ""]
        for name, (prefix, suffix) in theme["frames"].items():
            preview_lines.append(f"  {name}: {prefix}Hello World{suffix}")
        preview_path = pack_dir / "preview.txt"
        preview_path.write_text("\n".join(preview_lines), encoding="utf-8")

        # README
        readme_lines = [
            f"# {theme['name_ja']}",
            f"# {theme['name_en']}",
            "",
            "VRChat Chatbox Decorator 拡張フレームパック",
            "",
            "## 使い方 / Usage",
            "",
            "frames.json を Chatbox Decorator の FRAMES に追加してください。",
            "Add frames.json entries to Chatbox Decorator's FRAMES dictionary.",
            "",
            "## 収録フレーム / Included Frames",
            "",
        ]
        for name, (prefix, suffix) in theme["frames"].items():
            readme_lines.append(f"- **{name}**: {prefix}text{suffix}")
        readme_path = pack_dir / "README.txt"
        readme_path.write_text("\n".join(readme_lines), encoding="utf-8")

        return Asset(
            id=f"frame_pack_{theme_id}",
            agent=self.name,
            type="text/json",
            path=str(frames_path),
            monetization="direct_sale",
            estimated_value_yen=100.0,
            metadata={
                "product_type": "frame_pack",
                "theme": theme_id,
                "name_ja": theme["name_ja"],
                "name_en": theme["name_en"],
                "frame_count": len(theme["frames"]),
            },
        )

    def _generate_fortune_pack(
        self, theme_id: str, output_dir: Path
    ) -> Asset | None:
        """おみくじデータパックを生成する。"""
        theme = FORTUNE_THEMES[theme_id]
        pack_dir = output_dir / "fortune_packs" / theme_id
        pack_dir.mkdir(parents=True, exist_ok=True)

        fortune_data = {
            "theme_id": theme_id,
            "name_ja": theme["name_ja"],
            "name_en": theme["name_en"],
            "fortunes": theme["fortunes"],
            "lucky_items": theme["lucky_items"],
            "advice": theme["advice"],
        }
        fortune_path = pack_dir / "fortune_data.json"
        with open(fortune_path, "w", encoding="utf-8") as f:
            json.dump(fortune_data, f, ensure_ascii=False, indent=2)

        # README
        readme_lines = [
            f"# {theme['name_ja']}",
            f"# {theme['name_en']}",
            "",
            "VRChat おみくじBot 拡張データパック",
            "",
            "## 使い方 / Usage",
            "",
            "fortune_data.json を おみくじBot に読み込ませてください。",
            "",
            "## 収録内容 / Contents",
            "",
            f"- 運勢: {len(theme['fortunes'])}種類",
            f"- ラッキーアイテム: {len(theme['lucky_items'])}種類",
            f"- アドバイス: {len(theme['advice'])}種類",
        ]
        readme_path = pack_dir / "README.txt"
        readme_path.write_text("\n".join(readme_lines), encoding="utf-8")

        return Asset(
            id=f"fortune_pack_{theme_id}",
            agent=self.name,
            type="text/json",
            path=str(fortune_path),
            monetization="direct_sale",
            estimated_value_yen=100.0,
            metadata={
                "product_type": "fortune_pack",
                "theme": theme_id,
                "name_ja": theme["name_ja"],
                "name_en": theme["name_en"],
                "fortune_count": len(theme["fortunes"]),
                "item_count": len(theme["lucky_items"]),
            },
        )

    def _generate_footstep_prompts(
        self, theme_id: str, output_dir: Path
    ) -> Asset | None:
        """足音プロンプト拡張パックを生成する。"""
        theme = FOOTSTEP_EXPANSION_THEMES[theme_id]
        pack_dir = output_dir / "footstep_prompts" / theme_id
        pack_dir.mkdir(parents=True, exist_ok=True)

        prompt_data = {
            "theme_id": theme_id,
            "name_ja": theme["name_ja"],
            "prompts": theme["prompts"],
        }
        prompt_path = pack_dir / "prompts.json"
        with open(prompt_path, "w", encoding="utf-8") as f:
            json.dump(prompt_data, f, ensure_ascii=False, indent=2)

        return Asset(
            id=f"footstep_prompts_{theme_id}",
            agent=self.name,
            type="text/json",
            path=str(prompt_path),
            monetization="direct_sale",
            estimated_value_yen=50.0,
            metadata={
                "product_type": "footstep_prompts",
                "theme": theme_id,
                "name_ja": theme["name_ja"],
                "prompt_count": len(theme["prompts"]),
            },
        )

    def run(self, ctx: Context) -> list[Asset]:
        assets: list[Asset] = []
        generated = 0

        # 1. フレームパック
        for theme_id in self._find_missing_frame_themes(ctx.catalog):
            if generated >= self.max_per_cycle:
                break
            asset = self._generate_frame_pack(theme_id, ctx.output_dir)
            if asset:
                assets.append(asset)
                generated += 1
                logger.info(f"[catalog_expander] フレームパック生成: {theme_id}")

        # 2. おみくじパック
        for theme_id in self._find_missing_fortune_themes(ctx.catalog):
            if generated >= self.max_per_cycle:
                break
            asset = self._generate_fortune_pack(theme_id, ctx.output_dir)
            if asset:
                assets.append(asset)
                generated += 1
                logger.info(f"[catalog_expander] おみくじパック生成: {theme_id}")

        # 3. 足音プロンプト拡張
        for theme_id in self._find_missing_footstep_themes(ctx.catalog):
            if generated >= self.max_per_cycle:
                break
            asset = self._generate_footstep_prompts(theme_id, ctx.output_dir)
            if asset:
                assets.append(asset)
                generated += 1
                logger.info(f"[catalog_expander] 足音プロンプト生成: {theme_id}")

        if not assets:
            logger.info("[catalog_expander] 全バリエーション生成済み")

        return assets

    def estimate_value(self, catalog: Any) -> float:
        missing_frames = len(self._find_missing_frame_themes(catalog))
        missing_fortunes = len(self._find_missing_fortune_themes(catalog))
        missing_footsteps = len(self._find_missing_footstep_themes(catalog))
        total_missing = missing_frames + missing_fortunes + missing_footsteps
        # 未生成が多いほど価値が高い（カタログ拡大の余地がある）
        return total_missing * 100.0
