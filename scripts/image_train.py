"""
Train a diffusion model on images.
"""
import os
import argparse
import json

import torch as th

import decomp_diffusion.util.logger as logger
import decomp_diffusion.util.dist_util as dist_util

from decomp_diffusion.image_datasets import load_data
from decomp_diffusion.model import *
from decomp_diffusion.train_util import run_loop
from decomp_diffusion.diffusion.gaussian_diffusion import *
from decomp_diffusion.model_and_diffusion_util import *

from global_states import global_state

# fix randomness
th.manual_seed(0)
np.random.seed(0)

DEFAULT_IM = dict(
    clevr='sample_images/clevr_im_10.png',
    mnist='sample_images/mnist_digit_4.png',
    clevr_toy='im_8_clevr_toy.png',
    celebahq='im_19_celebahq.jpg',
    falcor3d='im_10_falcor3d.png',
    kitti='im_41_kitti.png',
    vkitti='im_12_vkitti.jpg',
    comb_kitti='im_41_kitti.png', # same as kitti
    tetris='im_6_tetris.png',
    anime='im_8_anime.jpg',
    faces='im_19_celebahq.jpg'
)

def main():
    args = create_argparser().parse_args()

    log_folder = args.log_folder
    model_desc = args.model_desc
    num_images = int(args.num_images) if (args.num_images is not None) else None
    predict_xstart = args.predict_xstart
    dataset = args.dataset
    downweight = args.downweight
    image_size = args.image_size
    use_dist = args.use_dist
    num_components = args.num_components
    num_run = args.num_run
    global_state.set_num_components(num_components)

    # log args

    if use_dist:
        dist_util.setup_dist()

    predict_desc = 'xstart' if predict_xstart else 'eps'
    save_desc = f'{model_desc}_{dataset}_{num_images}_{predict_desc}_emb_{args.emb_dim}_n{num_components}_v{num_run}'
    p_uncond = args.p_uncond
    if p_uncond > 0:
        save_desc += '_free'
    if len(args.extra_desc) > 0:
        save_desc += '_' + args.extra_desc

    if log_folder is None:
        log_folder = 'logs_' + save_desc

    os.makedirs(log_folder, exist_ok=True)
    logger.configure(log_folder)
    
    logger.log("creating model and diffusion...")

    if model_desc == 'unet_model':
        training_model_defaults = unet_model_defaults()
    elif model_desc == 'unet_model_cls':
        training_model_defaults = unet_model_cls_defaults()
    else:
        training_model_defaults = model_defaults()
    
    model_kwargs = args_to_dict(args, training_model_defaults.keys())

    model = create_diffusion_model(**model_kwargs)
    if use_dist:
        model.to(dist_util.dev())
    else:
        model.to('cuda')

    diffusion_kwargs = args_to_dict(args, diffusion_defaults().keys())
    gd = create_gaussian_diffusion(**diffusion_kwargs)

    relevant_keys = list(training_model_defaults.keys()) +  list(diffusion_defaults().keys()) + list(training_defaults().keys())
    json.dump(args_to_dict(args, relevant_keys),
        open(os.path.join(log_folder, 'arguments.json'), "w"), sort_keys=True, indent=4)
    logger.log("creating data loader...")

    data = load_data(
        base_dir=args.data_dir,
        dataset_type=dataset,
        batch_size=args.batch_size,
        image_size=image_size,
        num_images=num_images
    )
    
    logger.log("training...")

    default_im = DEFAULT_IM[dataset]

    start_epoch = 0
    if len(args.resume_checkpoint) > 0:
        ckpt_path = args.resume_checkpoint
        print(f'loading from {ckpt_path}')
        checkpoint = th.load(ckpt_path, map_location='cpu')
        model.load_state_dict(checkpoint)
        start_epoch = parse_epoch(ckpt_path)
        print(f'resuming from {start_epoch}')
    
    run_loop(model, gd, data, save_desc, start_epoch=start_epoch, epoch_block=args.epoch_block, num_its=args.num_its, p_uncond=p_uncond, default_im=default_im, latent_orthog=args.latent_orthog, dataset=dataset, downweight=downweight, image_size=image_size, use_dist=use_dist)

def parse_epoch(ckpt_path):
    """ckpt path must be {save_dir}/model_{epoch}.pt or {save_dir}/ema_{ema_rate}_{epoch}.pt"""
    assert ckpt_path[-3:] == '.pt'
    end_idx = -3 # exclusive
    start_idx = end_idx
    while ckpt_path[start_idx] != '_':
        start_idx -= 1
    start_idx += 1 # start of num
    epoch = int(ckpt_path[start_idx : end_idx])
    return epoch

def training_defaults():
    return dict(
        dataset="clevr",
        log_folder=None,
        num_images=None,
        p_uncond=0.0,
        latent_orthog=False,
        extra_desc='',
        downweight=False,
        epoch_block=10000,
        num_its=200,
        use_dist=True, # default set up dist training
    )

def create_argparser():
    defaults = dict(
        data_dir="",
        schedule_sampler="uniform",
        lr=1e-4,
        weight_decay=0.0,
        lr_anneal_steps=0,
        batch_size=1,
        microbatch=-1,  # -1 disables microbatches
        ema_rate="0.9999",  # comma-separated list of EMA values
        log_interval=10,
        save_interval=10000,
        resume_checkpoint="",
        use_fp16=False,
        fp16_scale_growth=1e-3,
        use_ddp=True
    )

    defaults.update()
    defaults.update(training_defaults())
    defaults.update(model_defaults())
    defaults.update(diffusion_defaults())
    # if defaults['model_desc'] == 'unet_model':
    defaults.update(unet_model_defaults())
    # elif defaults['model_desc'] == 'unet_model_cls':
    #     defaults.update(unet_model_cls_defaults())
    parser = argparse.ArgumentParser()
    add_dict_to_argparser(parser, defaults)
    print("Default arguments:")
    for key, value in defaults.items():
        print(f"{key}: {value}")
    return parser


if __name__ == "__main__":
    main()


