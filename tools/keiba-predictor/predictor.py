"""予測エンジン — 統計ベース予測と機械学習ベース予測"""

import os
import pickle


class StatisticalPredictor:
    """加重スコアリングによる予測（学習不要・即使用可能）"""

    FEATURE_WEIGHTS = {
        "horse_win_rate": 0.08,
        "horse_top3_rate": 0.06,
        "horse_win_rate_last5": 0.14,
        "horse_top3_rate_last5": 0.10,
        "venue_win_rate": 0.08,
        "surface_win_rate": 0.07,
        "distance_win_rate": 0.08,
        "condition_top3_rate": 0.05,
        "jockey_win_rate": 0.07,
        "jockey_top3_rate": 0.04,
        "jockey_venue_win_rate": 0.05,
        "running_style_score": 0.04,
        "gate_bias_score": 0.03,
        "rest_score": 0.04,
    }

    # 上がり3Fは低いほど良いので別途処理
    LAST_3F_WEIGHT = 0.07

    def predict(self, features_list):
        """全出走馬のスコアを計算してランキング順に返す

        Args:
            features_list: compute_all_features() の結果

        Returns:
            list[dict]: スコア付き・ランキング順の馬リスト
        """
        scored = []
        for feat in features_list:
            score = 0.0
            for key, w in self.FEATURE_WEIGHTS.items():
                score += feat.get(key, 0.0) * w

            # 上がり3F: 33秒台=高スコア、37秒台=低スコア
            last_3f = feat.get("avg_last_3f", 36.0)
            last_3f_score = max(0.0, min(1.0, (37.0 - last_3f) / 4.0))
            score += last_3f_score * self.LAST_3F_WEIGHT

            # 斤量ペナルティ
            weight_diff = feat.get("weight_diff", 0.0)
            score -= weight_diff * 0.005

            scored.append({
                "horse_name": feat["horse_name"],
                "horse_number": feat["horse_number"],
                "horse_id": feat["horse_id"],
                "jockey_name": feat["jockey_name"],
                "score": score,
                "features": feat,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # スコアを0〜1に正規化
        if scored:
            max_score = scored[0]["score"]
            min_score = scored[-1]["score"]
            spread = max_score - min_score
            if spread > 0:
                for s in scored:
                    s["normalized_score"] = (s["score"] - min_score) / spread
            else:
                for s in scored:
                    s["normalized_score"] = 0.5

        return scored


class MLPredictor:
    """機械学習ベースの予測（scikit-learn使用・要学習）"""

    FEATURE_KEYS = [
        "horse_win_rate", "horse_top3_rate",
        "horse_win_rate_last5", "horse_top3_rate_last5",
        "horse_avg_position_last5",
        "venue_win_rate", "surface_win_rate", "distance_win_rate",
        "condition_top3_rate", "avg_last_3f",
        "jockey_win_rate", "jockey_top3_rate", "jockey_venue_win_rate",
        "gate_bias_score", "weight_diff",
        "rest_score", "running_style_score",
    ]

    def __init__(self):
        self.model = None

    def _to_vector(self, feat):
        return [feat.get(k, 0.0) for k in self.FEATURE_KEYS]

    def train(self, features_list, labels):
        """学習

        Args:
            features_list: 特徴量辞書のリスト
            labels: 各馬の正解ラベル（1=3着以内, 0=4着以下）
        """
        from sklearn.ensemble import GradientBoostingClassifier

        X = [self._to_vector(f) for f in features_list]
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        self.model.fit(X, labels)

    def predict(self, features_list):
        """予測

        Returns:
            list[dict]: 確率付き・ランキング順の馬リスト
        """
        if self.model is None:
            raise RuntimeError("モデルが学習されていません。先に train コマンドを実行してください。")

        X = [self._to_vector(f) for f in features_list]
        probas = self.model.predict_proba(X)

        # クラス1（3着以内）の確率を取得
        class_idx = list(self.model.classes_).index(1) if 1 in self.model.classes_ else 0

        scored = []
        for feat, proba in zip(features_list, probas):
            scored.append({
                "horse_name": feat["horse_name"],
                "horse_number": feat["horse_number"],
                "horse_id": feat["horse_id"],
                "jockey_name": feat["jockey_name"],
                "score": proba[class_idx],
                "normalized_score": proba[class_idx],
                "features": feat,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def save(self, path):
        """モデルを保存"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.model, f)

    def load(self, path):
        """モデルを読み込み"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"モデルファイルが見つかりません: {path}")
        with open(path, "rb") as f:
            self.model = pickle.load(f)


def train_ml_model(races, data_dir="sample_data"):
    """過去データからMLモデルを学習する

    各レースの各馬について特徴量を計算し、3着以内かどうかをラベルとして学習。
    """
    from feature_engine import compute_horse_features
    from data_manager import get_race_info

    # レースIDごとにグループ化
    race_groups = {}
    for r in races:
        rid = r["race_id"]
        if rid not in race_groups:
            race_groups[rid] = []
        race_groups[rid].append(r)

    all_features = []
    all_labels = []

    # 各レースの各馬について特徴量を計算
    race_ids = sorted(race_groups.keys())
    for rid in race_ids:
        entries = race_groups[rid]
        race_info = {
            "race_id": entries[0]["race_id"],
            "race_date": entries[0]["race_date"],
            "venue": entries[0]["venue"],
            "race_number": entries[0]["race_number"],
            "race_name": entries[0]["race_name"],
            "grade": entries[0]["grade"],
            "distance": entries[0]["distance"],
            "surface": entries[0]["surface"],
            "track_condition": entries[0]["track_condition"],
            "weather": entries[0]["weather"],
        }

        for entry in entries:
            if entry["finish_position"] == 0:
                continue
            features = compute_horse_features(races, entry, race_info)
            features["horse_name"] = entry["horse_name"]
            features["horse_number"] = entry["horse_number"]
            features["horse_id"] = entry["horse_id"]
            features["jockey_name"] = entry["jockey_name"]
            all_features.append(features)
            all_labels.append(1 if entry["finish_position"] <= 3 else 0)

    if not all_features:
        raise ValueError("学習に使えるデータがありません")

    predictor = MLPredictor()
    predictor.train(all_features, all_labels)

    positive = sum(all_labels)
    negative = len(all_labels) - positive
    print(f"学習データ: {len(all_labels)}件（3着以内: {positive}件 / 4着以下: {negative}件）")

    return predictor
