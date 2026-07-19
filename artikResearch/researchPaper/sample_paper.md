# Deep Learning for Early Detection of Crop Disease from Leaf Images

Authors: Jane Doe, John Smith
Affiliation: Department of Computer Science, Example University

## Abstract
We present a convolutional neural network approach for early detection of crop disease
from smartphone leaf images. On a dataset of 12,000 images across 5 crops, our model reaches
94.2% accuracy, outperforming a ResNet-50 baseline by 3.1 points. The method runs on-device
in under 40ms, enabling field use without connectivity.

## Introduction
Crop disease causes major yield loss. Early detection enables timely intervention...

## Methods
We collected 12,000 labeled leaf images. The model is a lightweight CNN with depthwise
separable convolutions trained with focal loss...

## Results
The model achieves 94.2% top-1 accuracy and 0.93 macro-F1. Table 1 reports per-crop metrics.
Figure 1 shows the confusion matrix.

## Conclusion
On-device early crop-disease detection is feasible and accurate.

## References
[1] K. He et al., Deep Residual Learning for Image Recognition, CVPR 2016.
[2] M. Sandler et al., MobileNetV2, CVPR 2018.
