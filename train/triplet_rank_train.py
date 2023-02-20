import os
import os.path as ops
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import torch
from torch.autograd import Variable
from torch.utils.data import DataLoader
import torch.optim as optim
from torchvision import models
from rank_dataset import CustomDatasetFromImages
from torchvision.transforms import ToTensor, Resize, Compose, Pad, RandomHorizontalFlip, CenterCrop, RandomCrop, ToPILImage 
from torchvision.transforms import ToPILImage
import sys
from tqdm import tqdm
from model import resnet18_encoder, densenet121_encoder, mobilenet_encoder,regnet_x_400mf_encoder, efficientnet_b0_encoder,swin_v2_t_encoder
import argparse
import torchvision.transforms as T
from torch.optim.lr_scheduler import CosineAnnealingLR

import torchvision.models

os.environ['CUDA_VISIBLE_DEVICES']='0,1'


arguments = argparse.ArgumentParser()
arguments.add_argument('--lr', type=float, default=0.001)
arguments.add_argument('--momentum', type=float, default=0.9)
arguments.add_argument('--num_workers', type=int, default=12)
arguments.add_argument('--batch_size', type=int, default=48)
arguments.add_argument('--num_epoch', type=int, default=50)
arguments.add_argument('--spacing_size', type=int, default=1)
arguments.add_argument('--random_seed', type=int, default=123)
arguments.add_argument('--encoder_arc', type=str, default="resnet18_encoder")
arguments.add_argument('--optimizer', type=str, default="SGD")
arguments.add_argument('--add_augs', type=bool, default=False)
args = arguments.parse_args()


batch_size = args.batch_size
epoch = args.num_epoch
save_path = 'model_save/'

#normalize for ImageNet
normalize = torchvision.transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])

crop = 200
rng = np.random.RandomState(args.random_seed)
precrop = crop + 24
crop = rng.randint(crop, precrop)

jitter_aug = T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1, hue=0.1)
rot_aug = T.RandomRotation(degrees=(-30, 30))

transformations = Compose([
            Resize((256,256)),
            Pad((24,24,24,24))] + 
            ([jitter_aug, rot_aug] if args.add_augs else []) 
            + [CenterCrop(precrop),
            RandomCrop(crop),
            Resize((256,256)), 
            ToTensor(),
            normalize])

#define a batch-wise l2 loss
def criterion_l2(input_f, target_f):
    # return a per batch l2 loss
    res = (input_f - target_f)
    res = res * res
    return res.sum(dim=2)

def criterion_l2_2(input_f, target_f):
    # return a per batch l2 loss
    res = (input_f - target_f)
    res = res * res
    return res.sum(dim=1)

def criterion_cos(input_f, target_f):
    cos = nn.CosineSimilarity(dim=2, eps=1e-6)
    return cos(input_f, target_f)

def criterion_cos2(input_f, target_f):
    cos = nn.CosineSimilarity(dim=1, eps=1e-6)
    return cos(input_f, target_f)

def tuplet_loss(anchor, close, sequence):
    """
    N-tupled Loss
    one positive, multiple negative samples
    """
    delta = 3e-2 * torch.ones(anchor.size(0), device='cuda')
    # N x 10 x 256
    anchors = torch.unsqueeze(anchor, dim=1)  
    positives = torch.unsqueeze(close, dim=1)  

    close_distance = criterion_l2(anchors, positives).view(-1)
    far_distance = criterion_l2(anchors.expand(sequence.size(0), 10, 256), sequence)
    loss = torch.max(torch.zeros(anchor.size(0), device='cuda'), (close_distance - far_distance[:,0] + delta))
    
    for i in range(1,10):
        loss += torch.max(torch.zeros(anchor.size(0), device='cuda'), (far_distance[:,i-1] - far_distance[:,i] + delta))
    
    return loss.mean()
    

torch.manual_seed(args.random_seed)
combine_sets = CustomDatasetFromImages(transformations, spacing=args.spacing_size)
train_size = int(0.8 * len(combine_sets))
test_size = len(combine_sets) - train_size
train_dataset, test_dataset = torch.utils.data.random_split(combine_sets, [train_size, test_size])

train_dataset_loader = torch.utils.data.DataLoader(dataset=train_dataset,
                                                batch_size=batch_size,
                                                shuffle=True, num_workers = args.num_workers)

test_dataset_loader = torch.utils.data.DataLoader(dataset=test_dataset,
                                                batch_size=batch_size,
                                                shuffle=True, num_workers = args.num_workers)
model = None
if args.encoder_arc == "resnet18_encoder":#2015
    model = resnet18_encoder()
elif args.encoder_arc == "mobilenet_encoder":#2018
    model = mobilenet_encoder()
elif args.encoder_arc == "densenet121_encoder":#2016
    model = densenet121_encoder()




elif args.encoder_arc == "swin_v2_t":#2022
    model = swin_v2_t_encoder()#efficientnet_b0_encoder, efficientnet_b0_encoder,swin_v2_t_encoder#torchvision.models.swin_v2_t()
elif args.encoder_arc == "efficientnet_b0":#2019
    model = efficientnet_b0_encoder() #torchvision.models.efficientnet_b0()
elif args.encoder_arc == "regnet_x_400mf":
    model = regnet_x_400mf_encoder()#torchvision.models.regnet_x_400mf()
#elif args.encoder_arc == "regnet_y_400mf":#2020
    #model = torchvision.models.regnet_y_400mf()
#elif args.encoder_arc == "shufflenet_v2_x1_0":
    #model = torchvision.models.shufflenet_v2_x1_0()
#elif args.encoder_arc == "shufflenet_v2_x0_5":#2018
    #model = torchvision.models.shufflenet_v2_x0_5()


"""
 output = nn.functional.adaptive_avg_pool2d(output, 1).reshape(output.shape[0], -1)
        output = torch.flatten(output, 1)
        output = self.fc1(output)
        output = F.normalize(output, p=2, dim=1)

"""
#model = torch.nn.DataParallel(model, device_ids=[0,1])
model.cuda()

if args.optimizer == "SGD":
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)
elif args.optimizer == "Adam":
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
elif args.optimizer == "AdamW":
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

train_loss_list = []
test_acc_list = []
test_loss_list = []




def checkpoint(model, my_save_path, epoch):
    print ("save model, current epoch:{0}".format(epoch))    
    save_epoch = epoch + 0
    final_save_path = my_save_path + '_' + str(save_epoch) + '.pth'
    checkpoint_state = {
            'state_dict' : model.state_dict(), 
            'optimizer' : optimizer.state_dict()
            }

    torch.save(checkpoint_state, final_save_path)

scheduler = CosineAnnealingLR(optimizer, T_max = args.num_epoch * len(train_dataset_loader), eta_min=0.0001)

def train_model(model, epoches):
    total_loss = 0
    for i, (batch, label) in enumerate(tqdm(train_dataset_loader)):
        optimizer.zero_grad()
        input_images = Variable(batch[0]).cuda()
        close_images = Variable(batch[1]).cuda()
        far_images = Variable(torch.stack(batch[2:], dim=1)).cuda().view(-1, 3, 256, 256)

        input_emb = model(input_images)
        close_emb = model(close_images)
        far_emb = model(far_images).view(input_emb.size(0),-1, 256)

        loss = tuplet_loss(input_emb, close_emb, far_emb)
        loss.backward()
        optimizer.step()
        scheduler.step()
        total_loss += loss.cpu().detach().numpy()

    total_loss = total_loss * 1.0 / len(train_dataset_loader)
    train_loss_list.append(total_loss)
    print("train loss at the epoch %d is %f"%(epoches, total_loss))



def test_model(model, epoches):
    with torch.no_grad():
        total_loss = 0
        sep_acc = np.zeros(10)
        for i, (batch, label) in enumerate(tqdm(test_dataset_loader)):
            input_images = Variable(batch[0]).cuda()
            close_images = Variable(batch[1]).cuda()
            far_images = Variable(torch.stack(batch[2:], dim=1)).cuda().view(-1, 3, 256, 256)
            #torchvision.utils.save_image(far_images[0:10,:,:,:].data, 'test.png')

            input_emb = model(input_images)
            close_emb = model(close_images)
            far_emb = model(far_images).view(input_emb.size(0),-1, 256)

            loss = tuplet_loss(input_emb, close_emb, far_emb)
            total_loss += loss.cpu().detach().numpy()

            far_emb = far_emb.permute(1,0,2)
            close_dist = criterion_l2_2(input_emb, close_emb)
            far_dist = criterion_l2_2(input_emb, far_emb[0,:, :])
            diff = -close_dist + far_dist
            diff = diff.cpu().numpy()
            correct_index = np.where(diff > 0.0)[0]
            sep_acc[0] += correct_index.shape[0] * 1.0 / batch_size

            for i in range(1, 10):
                far_dist = criterion_l2_2(input_emb, far_emb[i,:,:])
                close_dist = criterion_l2_2(input_emb, far_emb[i-1,:,:])
                diff = -close_dist + far_dist
                diff = diff.cpu().numpy()
                correct_index2 = np.where(diff > 0.0)[0]
                sep_acc[i] += correct_index2.shape[0] * 1.0 / batch_size
            
        sep_acc /= len(test_dataset_loader)
        total_loss = total_loss * 1.0 / len(test_dataset_loader)
        total_acc = np.mean(sep_acc)

        print("test accuracy at the is %f"%(total_acc))
        print("test loss at the epoch %d is %f"%(epoches, total_loss))
        print("test sep acc at the epoc", sep_acc)

        test_acc_list.append(total_acc)
        test_loss_list.append(total_loss)
        

        
if __name__ == '__main__':
    # check first
    model.eval()
    test_model(model, -1)

    for i in range(epoch):
        model.train()
        train_model(model, i)

        model.eval()
        test_model(model, i)

        checkpoint(model,save_path, i)

    print(test_acc_list)
    print(test_loss_list)
    test_acc_list = np.array(test_acc_list)
    test_loss_list = np.array(test_loss_list)

    np.savez_compressed(save_path + 'loss_logger', testa=test_acc_list, testl=test_loss_list)

