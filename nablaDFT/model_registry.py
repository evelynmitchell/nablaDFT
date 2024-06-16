import json
import importlib
from copy import deepcopy
from typing import Dict
from pathlib import Path
from typing import List

import hydra
import torch
import pytorch_lightning as pl
from omegaconf import DictConfig, OmegaConf

import nablaDFT
from nablaDFT.utils import download_file


class ModelRegistry:
    """Source of pretrained model."""

    default_ckpt_dir = Path("./checkpoints")

    def __init__(self):
        with open(nablaDFT.__path__[0] + "/links/models_checkpoints.json", "r") as fin:
            content = json.load(fin)
        self._model_checkpoints = content['checkpoints']
        self._model_checkpoints_etag = content['etag']

        self._pretrained_model_cfg = {
            "lightning": {},
            "torch": {}
        }
        cfg_paths = (Path(nablaDFT.__path__[0]) / "../config/model/").glob("*")
        for cfg_path in cfg_paths:
            cfg = OmegaConf.load(cfg_path)
            self._pretrained_model_cfg[cfg.model_name] = cfg

    def get_pretrained_model_url(self, model_name: str) -> str:
        """Returns URL for given pretrained model name.

        Args:
            model_name (str): pretrained model name. Available models can be listed with :meth:nablaDFT.registry.ModelRegistry.list_models
        """
        url = self._model_checkpoints.get(model_name, None)
        if url:
            return self._model_checkpoints[model_name]
        else:
            raise KeyError(f"Wrong checkpoint name: {model_name}")

    def get_pretrained_model_etag(self, model_name: str) -> str:
        """Returns reference ETag for given pretrained model name.

        Args:
            model_name (str): pretrained model name. Available models can be listed with :meth:nablaDFT.registry.ModelRegistry.list_models
        """
        return self._model_checkpoints_etag[model_name]

    def list_models(self) -> List[str]:
        """Returns all available pretrained on nablaDFT model checkpoints."""
        return list(self._model_checkpoints.keys())

    def get_pretrained_model(self, model_type: str, model_name: str):
        """Instantiates model and restores model's state from checkpoint.

        Downloads model checkpoint if necessary.

        Args:
            model_type (str): model framework, must be one of ["torch", "lightning"]
            model_name (str): model checkpoint name. Available models can be listed with :meth:nablaDFT.registry.ModelRegistry.list_models
        """
        backbone_name = model_name.split("_")[0]
        model_cfg = self._pretrained_model_cfg[backbone_name]
        ckpt_path = self.default_ckpt_dir / model_cfg.model_name / backbone_name
        if not ckpt_path.exists():
            download_file(
                self.get_pretrained_model_url(model_name),
                ckpt_path,
                self.get_pretrained_model_etag(model_name),
                desc=f"Downloading {model_name}"
            )
        if model_type == "torch":
            model = self._load_torch_model(model_cfg, ckpt_path)
        elif model_type == "lightning":
            model = self._load_lightning_model(model_cfg, ckpt_path)
        else:
            raise KeyError(f"Wrong model type: {model_type}, must be on of ['torch', 'lightning']")
        return model

    def _load_torch_model(self, cfg: DictConfig, ckpt_path: Path):
        model: torch.nn.Module = hydra.utils.instantiate(cfg.net)
        state_dict = self._rebuild_state_dict(torch.load(ckpt_path)["state_dict"])
        model.load_state_dict(state_dict)
        return model

    def _load_lightning_model(self, cfg: DictConfig, ckpt_path: Path):
        module, cls_name = ".".join(cfg._target_.split(".")[:-1]), cfg._target_.split(".")[-1]
        model_cls: pl.LightningModule = getattr(importlib.import_module(module), cls_name)
        torch_model: torch.nn.Module = hydra.utils.instantiate(cfg.net)
        model = model_cls.load_from_checkpoint(ckpt_path, net=torch_model)
        return model

    def _rebuild_state_dict(self, state_dict: Dict):
        new_state_dict = {}
        for key in state_dict.keys():
            new_key = ".".join(key.split(".")[1:])
            new_state_dict[new_key] = deepcopy(state_dict[key])
        return new_state_dict


model_registry = ModelRegistry()
