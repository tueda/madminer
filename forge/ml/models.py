from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import torch
import torch.nn as nn
from torch.autograd import grad

from forge.ml.utils import get_activation, general_init


class ParameterizedRatioEstimator(nn.Module):
    """ Module that implements agnostic parameterized likelihood estimators such as RASCAL or ALICES. Only the
    numerator of the ratio is parameterized. """

    def __init__(self, n_observables, n_parameters, n_hidden, activation='tanh'):

        super(ParameterizedRatioEstimator, self).__init__()

        # Save input
        self.n_hidden = n_hidden
        self.activation = get_activation(activation)

        # Build network
        self.layers = nn.ModuleList()
        n_last = n_observables + n_parameters

        # Hidden layers
        for n_hidden_units in n_hidden:
            self.layers.append(
                nn.Linear(n_last, n_hidden_units)
            )
            n_last = n_hidden_units

        # Log r layer
        self.layers.append(
            nn.Linear(n_last, 1)
        )

    def forward(self, theta, x, track_score=True):

        """
        Calculates estimated log likelihood ratio and the derived score.

        :param theta:
        :param x:
        :param track_score:
        :return: s_hat, log_r_hat, t_hat
        """

        # Track gradient wrt theta
        if track_score and not theta.requires_grad:  # Can this happen?
            theta.requires_grad = True

        # log r estimator
        log_r_hat = torch.cat((theta, x), 1)

        for i, layer in enumerate(self.layers):
            if i > 0:
                log_r_hat = self.activation(log_r_hat)
            log_r_hat = layer(log_r_hat)

        # Bayes-optimal s
        s_hat = 1. / (1. + torch.exp(log_r_hat))

        # Score t
        if track_score:
            t_hat = grad(log_r_hat, theta,
                         grad_outputs=torch.ones_like(log_r_hat.data),
                         only_inputs=True, create_graph=True)[0]
        else:
            t_hat = None

        return s_hat, log_r_hat, t_hat

    def to(self, *args, **kwargs):
        self = super().to(*args, **kwargs)

        for i, layer in enumerate(self.layers):
            self.layers[i] = layer.to(*args, **kwargs)

        return self


class DoublyParameterizedRatioEstimator(nn.Module):
    """ Module that implements agnostic parameterized likelihood estimators such as RASCAL or ALICES. Both
    numerator and denominator of the ratio are parameterized.

    Ideas:
    - ensure antisymmetric property log_r_hat(theta0, theta1, x) = - log_r_hat(theta1, theta0, x):
        - regulator
        - weight sharing?
          l = f(A * theta0 + B * theta1 + C  * x)
          Clearly B = -A ensures antisymmetry, but then we are _only_ sensitive to theta0 - theta1
    - train with many theta for each generated event (only possible w/ morphing)
    """

    def __init__(self, n_observables, n_parameters, n_hidden, activation='tanh'):

        super(ParameterizedRatioEstimator, self).__init__()

        # Save input
        self.n_hidden = n_hidden
        self.activation = get_activation(activation)

        # Build network
        self.layers = nn.ModuleList()
        n_last = n_observables + n_parameters

        # Hidden layers
        for n_hidden_units in n_hidden:
            self.layers.append(
                nn.Linear(n_last, n_hidden_units)
            )
            n_last = n_hidden_units

        # Log r layer
        self.layers.append(
            nn.Linear(n_last, 1)
        )

    def forward(self, theta0, theta1, x, track_scores=True):

        """
        Calculates estimated log likelihood ratio and the derived score.

        :param theta:
        :param x:
        :param track_score:
        :return: s_hat, log_r_hat, t_hat0, t_hat1
        """

        # Track gradient wrt thetas
        if track_scores and not theta0.requires_grad:
            theta0.requires_grad = True
        if track_scores and not theta1.requires_grad:
            theta1.requires_grad = True

        # log r estimator
        log_r_hat = torch.cat((theta0, theta1, x), 1)

        for i, layer in enumerate(self.layers):
            if i > 0:
                log_r_hat = self.activation(log_r_hat)
            log_r_hat = layer(log_r_hat)

        # Bayes-optimal s
        s_hat = 1. / (1. + torch.exp(log_r_hat))

        # Score t
        if track_scores:
            t_hat0 = grad(log_r_hat, theta0,
                          grad_outputs=torch.ones_like(log_r_hat.data),
                          only_inputs=True, create_graph=True)[0]
            t_hat1 = grad(log_r_hat, theta1,
                          grad_outputs=torch.ones_like(log_r_hat.data),
                          only_inputs=True, create_graph=True)[0]
        else:
            t_hat0 = None
            t_hat1 = None

        return s_hat, log_r_hat, t_hat0, t_hat1

    def to(self, *args, **kwargs):
        self = super().to(*args, **kwargs)

        for i, layer in enumerate(self.layers):
            self.layers[i] = layer.to(*args, **kwargs)

        return self