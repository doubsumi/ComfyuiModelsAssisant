"""内置架构定义（首次启动时写入 data/architectures.json）"""

ARCHITECTURES_CONTENT = r"""{
  "version": "1.0.0",
  "architectures": {
    "flux": {
      "label": "FLUX.1",
      "unetFolder": "diffusion_models",
      "encoders": ["clip_l.safetensors", "t5xxl_fp8_e4m3fn.safetensors"],
      "encoderNode": "DualCLIPLoader",
      "encoderNodeParams": { "type": "flux" },
      "vae": "ae.safetensors",
      "defaultParams": { "steps": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple" },
      "loraCompatibility": "flux"
    },
    "krea2": {
      "label": "Krea 2",
      "unetFolder": "diffusion_models",
      "encoders": ["qwen3vl_4b_fp8_scaled.safetensors"],
      "encoderNode": "CLIPLoader",
      "encoderNodeParams": { "type": "krea2" },
      "vae": "qwen_image_vae.safetensors",
      "defaultParams": { "steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple" },
      "loraCompatibility": "krea2"
    },
    "boogu": {
      "label": "Boogu Image",
      "unetFolder": "diffusion_models",
      "encoders": ["qwen3vl_8b_fp8_scaled.safetensors"],
      "encoderNode": "CLIPLoader",
      "encoderNodeParams": { "type": "boogu" },
      "vae": "ae.safetensors",
      "defaultParams": { "steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "sgm_uniform" },
      "loraCompatibility": "boogu"
    },
    "qwen_image": {
      "label": "Qwen-Image",
      "unetFolder": "diffusion_models",
      "encoders": ["qwen_2.5_vl_7b.safetensors"],
      "encoderNode": "CLIPLoader",
      "encoderNodeParams": { "type": "qwen_image" },
      "vae": "qwen_image_vae.safetensors",
      "defaultParams": { "steps": 14, "cfg": 2.5, "sampler": "euler", "scheduler": "beta" },
      "loraCompatibility": "qwen"
    },
    "minimax_h3_fl2va": {
      "label": "MiniMax H3 (FL2VA)",
      "unetFolder": "diffusion_models",
      "encoders": ["qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "qwen3vl_8b_fp8_scaled.safetensors", "qwen3vl_4b_fp8_scaled.safetensors"],
      "encoderNode": "CLIPLoader",
      "encoderNodeParams": { "type": "minimax" },
      "vae": ["minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
      "defaultParams": { "steps": 20, "cfg": 1.0, "sampler": "res_multistep", "scheduler": "simple" },
      "loraCompatibility": "minimax_h3"
    },
    "minimax_h3_ref2va": {
      "label": "MiniMax H3 (Ref2VA)",
      "unetFolder": "diffusion_models",
      "encoders": ["qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"],
      "encoderNode": "CLIPLoader",
      "encoderNodeParams": { "type": "minimax" },
      "vae": ["minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
      "defaultParams": { "steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple" },
      "loraCompatibility": "minimax_h3"
    },
    "sdxl": {
      "label": "SDXL",
      "unetFolder": "checkpoints",
      "encoders": [],
      "encoderNode": "CheckpointLoaderSimple",
      "encoderNodeParams": {},
      "vae": "sdxl_vae.safetensors",
      "defaultParams": { "steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras" },
      "loraCompatibility": "sdxl"
    },
    "sd15": {
      "label": "SD 1.5",
      "unetFolder": "checkpoints",
      "encoders": [],
      "encoderNode": "CheckpointLoaderSimple",
      "encoderNodeParams": {},
      "vae": "vae-ft-mse-840000-ema-pruned.safetensors",
      "defaultParams": { "steps": 25, "cfg": 7.0, "sampler": "euler_a", "scheduler": "normal" },
      "loraCompatibility": "sd15"
    }
  },
  "compatibilityMatrix": {
    "sd15":  { "compatibleLoras": ["sd15"],  "incompatibleLoras": ["sdxl","flux","krea2","boogu","qwen","minimax_h3"] },
    "sdxl":  { "compatibleLoras": ["sdxl"],  "incompatibleLoras": ["sd15","flux","krea2","boogu","qwen","minimax_h3"] },
    "flux":  { "compatibleLoras": ["flux"],  "incompatibleLoras": ["sd15","sdxl","krea2","boogu","qwen","minimax_h3"] },
    "krea2": { "compatibleLoras": ["krea2"], "incompatibleLoras": ["sd15","sdxl","flux","boogu","qwen","minimax_h3"] },
    "boogu": { "compatibleLoras": ["boogu"], "incompatibleLoras": ["sd15","sdxl","flux","krea2","qwen","minimax_h3"] },
    "qwen_image": { "compatibleLoras": ["qwen"], "incompatibleLoras": ["sd15","sdxl","flux","krea2","boogu","minimax_h3"] },
    "minimax_h3_fl2va": { "compatibleLoras": ["minimax_h3"], "incompatibleLoras": ["sd15","sdxl","flux","krea2","boogu","qwen"] },
    "minimax_h3_ref2va": { "compatibleLoras": ["minimax_h3"], "incompatibleLoras": ["sd15","sdxl","flux","krea2","boogu","qwen"] }
  }
}
"""
