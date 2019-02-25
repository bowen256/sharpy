import numpy as np
import scipy.linalg as sclalg
import sharpy.linear.src.libss as libss
import sharpy.utils.h5utils as h5


class ReducedOrderModel(object):
    """
    Reduced Order Model
    """

    def __init__(self):

        self.settings_types = dict()
        self.settings_default = dict()

        self.settings_types['algorithm'] = 'str'
        self.settings_default['algorithm'] = None

        self.settings_types['frequencies'] = 'list(complex)'
        self.settings_default['frequencies'] = None

        self.frequency = None
        self.algorithm = None
        self.ss = None
        self.r = 100
        self.V = None
        self.H = None
        self.W = None
        self.ssrom = None
        self.data = None
        self.sstype = None

    def initialise(self, data, ss):

        self.data = data
        self.ss = ss

        if self.ss.dt is None:
            self.sstype = 'ct'
        else:
            self.sstype = 'dt'

    def run(self, algorithm, r, frequency=None):
        self.algorithm = algorithm
        self.frequency = frequency
        self.r = r

        if algorithm == 'arnoldi':
            Ar, Br, Cr = self.one_sided_arnoldi(frequency, r)

        elif algorithm == 'two_sided_arnoldi':
            Ar, Br, Cr = self.two_sided_arnoldi(frequency, r)

        elif algorithm == 'dual_rational_arnoldi':
            Ar, Br, Cr = self.dual_rational_arnoldi_siso(frequency, r)

        elif algorithm == 'real_rational_arnoldi':
            Ar, Br, Cr = self.real_rational_arnoldi(frequency, r)

        else:
            raise NotImplementedError('Algorithm %s not recognised, check for spelling or it may not be implemented'
                                      %algorithm)

        self.ssrom = libss.ss(Ar, Br, Cr, self.ss.D, self.ss.dt)


    def one_sided_arnoldi(self, frequency, r):
        r"""
        One-sided Arnoldi method expansion about a single interpolation point, :math`\sigma`.
        The projection matrix :math:`\mathbf{V}` is constructed using an order :math:`r` Krylov space. The space for
        a single finite interpolation point known as a Pade approximation is described by:

            .. math::
                    \text{range}(\textbf{V}) = \mathcal{K}_r((\sigma\mathbf{I}_n - \mathbf{A})^{-1},
                    (\sigma\mathbf{I}_n - \mathbf{A})^{-1}\mathbf{b})

        In the case of an interpolation about infinity, the problem is known as partial realisation and the Krylov
        space is

            .. math::
                    \text{range}(\textbf{V}) = \mathcal{K}_r(\mathbb{A}, \mathbf{b})

        The resulting orthogonal projection leads to the following reduced order system:

            .. math::
                \hat{\Sigma} : \left(\begin{array}{c|c} \hat{A} & \hat{B} \\
                \hline \hat{C} & {D}\end{array}\right)
                \text{with } \begin{cases}\hat{A}=V^TAV\in\mathbb{R}^{k\times k},\,\\
                \hat{B}=V^TB\in\mathbb{R}^{k\times m},\,\\
                \hat{C}=CV\in\mathbb{R}^{p\times k},\,\\
                \hat{D}=D\in\mathbb{R}^{p\times m}\end{cases}


        Args:
            frequency (complex): Interpolation point :math:`\sigma \in \mathbb{C}`
            r (int): Number of moments to match. Equivalent to Krylov space order and order of the ROM.

        Returns:
            tuple: The reduced order model matrices: :math:`\mathbf{A}_r`, :math:`\mathbf{B}_r` and :math:`\mathbf{C}_r`

        """
        A = self.ss.A
        B = self.ss.B
        C = self.ss.C

        nx = A.shape[0]

        if frequency != np.inf and frequency is not None:
            lu_A = (frequency * np.eye(nx) - A)
            V = self.construct_krylov(r, lu_A, B, 'Pade', 'b')
        else:
            V = self.construct_krylov(r, A, B, 'partial_realisation', 'b')

        # Reduced state space model
        Ar = V.T.dot(A.dot(V))
        Br = V.T.dot(B)
        Cr = C.dot(V)

        return Ar, Br, Cr

    def two_sided_arnoldi(self, frequency, r):
        A = self.ss.A
        B = self.ss.B
        C = self.ss.C

        nx = A.shape[0]

        if frequency != np.inf and frequency is not None:
            lu_A = frequency * np.eye(nx) - A
            V = self.construct_krylov(r, lu_A, B, 'Pade', 'b')
            W = self.construct_krylov(r, lu_A, C.T, 'Pade', 'c')
        else:
            V = self.construct_krylov(r, A, B, 'partial_realisation', 'b')
            W = self.construct_krylov(r, A, C.T, 'partial_realisation', 'c')

        # Ensure oblique projection to ensure W^T V = I
        # lu_WW = sclalg.lu_factor(W.T.dot(V))
        # W1 = sclalg.lu_solve(lu_WW, W.T, trans=1).T # Verify
        W = W.dot(sclalg.inv(W.T.dot(V)).T)

        # Reduced state space model
        Ar = W.T.dot(A.dot(V))
        Br = W.T.dot(B)
        Cr = C.dot(V)

        return Ar, Br, Cr

    @staticmethod
    def construct_krylov(r, lu_A, B, approx_type='Pade', side='b'):
        r"""
        Contructs a Krylov subspace in an iterative manner following the methods of Gugercin [1].

        The construction of the Krylov space is focused on Pade and partial realisation cases for the purposes of model
        reduction. I.e. the partial realisation form of the Krylov space is used if
        ``approx_type = 'partial_realisation'``

            .. math::
                \text{range}(\textbf{V}) = \mathcal{K}_r(\mathbb{A}, \mathbf{b})

        Else, it is replaced by the Pade approximation form:

            .. math::
                \text{range}(\textbf{V}) = \mathcal{K}_r((\sigma\mathbf{I}_n - \mathbf{A})^{-1},
                (\sigma\mathbf{I}_n - \mathbf{A})^{-1}\mathbf{b})

        Note that no inverses are actually computed but rather a single LU decomposition is performed at the beginning
        of the algorithm. Forward and backward substitution is used thereinafter to calculate the required vectors.

        The algorithm also builds the Krylov space for the :math:`\mathbf{C}^T` matrix. It should simply replace ``B``
        and ``side`` should be ``side = 'c'``.

        Examples:
            Partial Realisation:

            ``V = construct_krylov(r, A, B, 'partial_realisation', 'b')``
            ``W = construct_krylov(r, A, C.T, 'partial_realisation', 'c')``

            Pade Approximation:

            ``V = construct_krylov(r, (sigma * np.eye(nx) - A), B, 'Pade', 'b')``
            ``W = construct_krylov(r, (sigma * np.eye(nx) - A), C.T, 'Pade', 'c')``


        References:
            [1]. Gugercin, S. - Projection Methods for Model Reduction of Large-Scale Dynamical Systems. PhD Thesis.
            Rice University. 2003.

        Args:
            r (int): Krylov space order
            lu_A (np.ndarray): For Pade approximations it should be :math:`(\sigma I - \mathbf{A})`.
                For partial realisations it is simply :math:`\mathbf{A}`.
            B (np.ndarray): If doing the B side it should be :math:`\mathbf{B}`, else :math:`\mathbf{C}`.
            approx_type (str): Type of approximation: ``partia_realisation`` or ``Pade``.
            side: Side of the projection ``b`` or ``c``.

        Returns:
            np.ndarray: Projection matrix

        """

        nx = B.shape[0]

        # Side indicates projection side. if using C then it needs to be transposed
        if side=='c':
            transpose_mode = 1
            B.shape = (B.shape[0], )
        else:
            transpose_mode = 0

        # Output projection matrices
        V = np.zeros((nx, r),
                     dtype=complex)
        H = np.zeros((r, r),
                     dtype=complex)

        # Declare iterative variables
        f = np.zeros((nx, r),
                     dtype=complex)

        if approx_type != 'partial_realisation':
            # LU decomposiotion
            lu_A = sclalg.lu_factor(lu_A)
            v = sclalg.lu_solve(lu_A, B, trans=transpose_mode)
            v = v / np.linalg.norm(v)

            w = sclalg.lu_solve(lu_A, v)
            # w = sclalg.inv((frequency * np.eye(nx) - A)).dot(v)
        else:
            A = lu_A
            v_arb = B
            v = v_arb / np.linalg.norm(v_arb)
            w = A.dot(v)

        alpha = v.T.dot(w)

        # Initial assembly
        f[:, 0] = w - v.dot(alpha)
        V[:, 0] = v
        H[0, 0] = alpha

        for j in range(0, r-1):

            beta = np.linalg.norm(f[:, j])
            v = 1 / beta * f[:, j]

            V[:, j+1] = v
            H_hat = np.block([[H[:j+1, :j+1]],
                             [beta * evec(j)]])

            if approx_type != 'partial_realisation':
                w = sclalg.lu_solve(lu_A, v, trans=transpose_mode)
            else:
                w = A.dot(v)

            h = V[:, :j+2].T.dot(w)
            f[:, j+1] = w - V[:, :j+2].dot(h)

            # Finite precision
            s = V[:, :j+2].T.dot(f[:, j+1])
            f[:, j+1] = f[:, j+1] - V[:, :j+2].dot(s)  #Confusing line in Gugercin's thesis where it states f_{j=1}?
            h += s

            h.shape = (j+2, 1)  # Enforce shape for concatenation
            H[:j+2, :j+2] = np.block([H_hat, h])

        return V


    def real_rational_arnoldi(self, frequency, r):
        """
        When employing complex frequencies, the projection matrix can be normalised to be real
        Following Algorithm 1b in Lee(2006)
        Args:
            frequency:
            r:

        Returns:

        """

        raise NotImplementedError('Real valued rational Arnoldi Method in progress')

        ### Not working, having trouble with the last column of H. need to investigate the background behind the creation of H and see hwat can be done

        A = self.ss.A
        B = self.ss.B
        C = self.ss.C

        nx = A.shape[0]
        nfreq = frequency.shape[0]

        # Columns of matrix v
        v_ncols = 2 * np.sum(r)

        # Output projection matrices
        V = np.zeros((nx, v_ncols),
                     dtype=float)
        H = np.zeros((v_ncols, v_ncols),
                     dtype=float)
        res = np.zeros((nx,v_ncols+2),
                       dtype=float)

        lu_A = sclalg.lu_factor(frequency[0] * np.eye(nx) - A)
        v_res = sclalg.lu_solve(lu_A, B)

        H[0, 0] = np.linalg.norm(v_res)
        V[:, 0] = v_res.real / H[0, 0]

        k = 0
        for i in range(nfreq):
            for j in range(r[i]):
                # k = 2*(i*r[i] + j)
                print("i = %g\t j = %g\t k = %g" % (i, j, k))

                # res[:, k] = np.imag(v_res)
                # if k > 0:
                #     res[:, k-1] = np.real(v_res)
                #
                # # Working on the last finished column i.e. k-1 only when k>0
                # if k > 0:
                #     for t in range(k):
                #         H[t, k-1] = V[:, t].T.dot(res[:, k-1])
                #         res[:, k-1] -= res[:, k-1] - H[t, k-1] * V[:, t]
                #
                #     H[k, k-1] = np.linalg.norm(res[:, k-1])
                #     V[:, k] = res[:, k-1] / H[k, k-1]
                #
                # # Normalise working column k
                # for t in range(k+1):
                #     H[t, k] = V[:, t].T.dot(res[:, k])
                #     res[:, k] -= H[t, k] * V[:, t]
                #
                # # Subdiagonal term
                # H[k+1, k] = np.linalg.norm(res[:, k])
                # V[:, k + 1] = res[:, k] / np.linalg.norm(res[:, k])
                #
                # if j == r[i] - 1 and i < nfreq - 1:
                #     lu_A = sclalg.lu_factor(frequency[i+1] * np.eye(nx) - A)
                #     v_res = sclalg.lu_solve(lu_A, B)
                # else:
                #     v_res = - sclalg.lu_solve(lu_A, V[:, k+1])

                if k == 0:
                    V[:, 0] = v_res.real / np.linalg.norm(v_res.real)
                else:
                    res[:, k] = np.imag(v_res)
                    res[:, k-1] = np.real(v_res)

                    for t in range(k):
                        H[t, k-1] = np.linalg.norm(res[:, k-1])
                        res[:, k-1] -= H[t, k-1]*V[:, t]

                    H[k, k-1] = np.linalg.norm(res[:, k-1])
                    V[:, k] = res[:, k-1] / H[k, k-1]

                if k == 0:
                    H[0, 0] = V[:, 0].T.dot(v_res.imag)
                    res[:, 0] -= H[0, 0] * V[:, 0]

                else:
                    for t in range(k+1):
                        H[t, k] = V[:, t].T.dot(res[:, k])
                        res[:, k] -= H[t, k] * V[:, t]
                H[k+1, k] = np.linalg.norm(res[:, k])
                V[:, k+1] = res[:, k] / H[k+1, k]

                if j == r[i] - 1 and i < nfreq - 1:
                    lu_A = sclalg.lu_factor(frequency[i+1]*np.eye(nx) - A)
                    v_res = sclalg.lu_solve(lu_A, B)
                else:
                    v_res = - sclalg.lu_solve(lu_A, V[:, k+1])

                k += 2

        # Add last column of H
        print(k)
        res[:, k-1] = - sclalg.lu_solve(lu_A, V[:, k-1])
        for t in range(k-1):
            H[t, k-1] = V[:, t].T.dot(res[:, k-1])
            res[:, k-1] -= H[t, k-1]*V[:, t]

        self.V = V
        self.H = H

        Ar = V.T.dot(A.dot(V))
        Br = V.T.dot(B)
        Cr = C.dot(V)

        return Ar, Br, Cr

    def dual_rational_arnoldi_siso(self, frequency, r):
        """
        Dual Rational Arnoli Interpolation for SISO sytems. Based on the methods of Grimme
        Args:
            frequency:
            r:

        Returns:

        """
        A = self.ss.A
        B = self.ss.B
        C = self.ss.C

        nx = A.shape[0]

        try:
            nfreq = frequency.shape[0]
        except AttributeError:
            nfreq = 1

        assert nfreq > 1, 'Dual Rational Arnoldi requires more than one frequency to interpolate'

        V = np.zeros((nx, r*nfreq), dtype=complex)
        W = np.zeros((nx, r*nfreq), dtype=complex)

        we = 0
        for i in range(nfreq):
            sigma = frequency[i]
            lu_A = sigma * np.eye(nx) - A
            V[:, we:we+r] = self.construct_krylov(r, lu_A, B, 'Pade', 'b')
            W[:, we:we+r] = self.construct_krylov(r, lu_A, C.T, 'Pade', 'c')

            we += r

        W = W.dot(sclalg.inv(W.T.dot(V)).T)
        self.W = W
        self.V = V

        # Reduced state space model
        Ar = W.T.dot(A.dot(V))
        Br = W.T.dot(B)
        Cr = C.dot(V)

        return Ar, Br, Cr




    # def compare_frequency_response(self, wv, return_error=False, plot_figures=False):
    #     """
    #     Computes the frequency response of the full and reduced models up to the Nyquist frequency
    #
    #     Returns:
    #
    #     """
        # if self.data is not None:
        #     Uinf0 = self.data.aero.timestep_info[0].u_ext[0][0, 0, 0]
        #     c_ref = self.data.aero.timestep_info[0].zeta[0][0, -1, 0] - self.data.aero.timestep_info[0].zeta[0][0, 0, 0]
        #     ds = 2. / self.data.aero.aero_dimensions[0][0]  # Spatial discretisation
        #     fs = 1. / ds
        #     fn = fs / 2.
        #     ks = 2. * np.pi * fs
        #     kn = 2. * np.pi * fn  # Nyquist frequency
        #     Nk = 151  # Number of frequencies to evaluate
        #     kv = np.linspace(1e-3, kn, Nk)  # Reduced frequency range
        #     wv = 2. * Uinf0 / c_ref * kv  # Angular frequency range
        # else:
        #     kv = wv
        #     c_ref = 2
        #     Uinf0 = 1
        #
        # frequency = self.frequency
        # # TODO to be modified for plotting purposes when using multi rational interpolation
        # try:
        #     nfreqs = frequency.shape[0]
        # except AttributeError:
        #     nfreqs = 1
        #
        # if frequency is None:
        #     k_rom = np.inf
        # else:
        #     if self.ss.dt is not None:
        #         ct_frequency = np.log(frequency)/self.ss.dt
        #         k_rom = c_ref * ct_frequency * 0.5 / Uinf0
        #     else:
        #         k_rom = c_ref * frequency * 0.5 / Uinf0
        #
        # display_frequency = '$\sigma$ ='
        # if nfreqs > 1:
        #     display_frequency += ' ['
        #     for i in range(nfreqs):
        #         if type(k_rom[i]) == complex:
        #             display_frequency += ' %.1f + %.1fj' % (k_rom[i].real, k_rom[i].imag)
        #         else:
        #             display_frequency += ' %.1f' % k_rom[i]
        #         display_frequency += ','
        #     display_frequency += ']'
        # else:
        #     if type(k_rom) == complex:
        #         display_frequency += ', %.1f + %.1fj' % (k_rom.real, k_rom.imag)
        #     else:
        #         display_frequency += ', %.1f' % k_rom
        #
        # nstates = self.ss.states
        # rstates = self.ssrom.states
        #
        # # Compute the frequency response
        # Y_full_system = self.ss.freqresp(wv)
        # Y_freq_rom = self.ssrom.freqresp(wv)
        #
        # rel_error = (Y_freq_rom[0, 0, :] - Y_full_system[0, 0, :]) / Y_full_system[0, 0, :]
        #
        #
        # if plot_figures:
        #     pass
        #     # In the process of getting it away from here.


            # phase_ss = np.angle((Y_full_system[0, 0, :])) # - (np.angle((Y_full_system[0, 0, :])) // np.pi) * 2 * np.pi
            # phase_ssrom = np.angle((Y_freq_rom[0, 0, :])) #- (np.angle((Y_freq_rom[0, 0, :])) // np.pi) * 2 * np.pi
            #
            # ax[0].semilogx(kv, np.abs(Y_full_system[0, 0, :]),
            #            lw=4,
            #            alpha=0.5,
            #            color='b',
            #            label='UVLM - %g states' % nstates)
            # ax[1].semilogx(kv, phase_ss, ls='-',
            #            lw=4,
            #            alpha=0.5,
            #            color='b')
            #
            # ax[1].set_xlim(0, kv[-1])
            # ax[0].grid()
            # ax[1].grid()
            # ax[0].semilogx(kv, np.abs(Y_freq_rom[0, 0, :]), ls='-.',
            #            lw=1.5,
            #            color='k',
            #            label='ROM - %g states' % rstates)
            # ax[1].semilogx(kv, phase_ssrom, ls='-.',
            #            lw=1.5,
            #            color='k')
            #
            # # axins0 = inset_axes(ax[0], 1, 1, loc=1)
            # # axins0.semilogx(kv, np.abs(Y_full_system[0, 0, :]),
            # #             lw=4,
            # #             alpha=0.5,
            # #             color='b')
            # # axins0.semilogx(kv, np.abs(Y_freq_rom[0, 0, :]), ls='-.',
            # #             lw=1.5,
            # #             color='k')
            # # axins0.set_xlim([0, 1])
            # # axins0.set_ylim([0, 0.1])
            # #
            # # axins1 = inset_axes(ax[1], 1, 1.25, loc=1)
            # # axins1.semilogx(kv, np.angle((Y_full_system[0, 0, :])), ls='-',
            # #             lw=4,
            # #             alpha=0.5,
            # #             color='b')
            # # axins1.semilogx(kv, np.angle((Y_freq_rom[0, 0, :])), ls='-.',
            # #             lw=1.5,
            # #             color='k')
            # # axins1.set_xlim([0, 1])
            # # axins1.set_ylim([-3.5, 3.5])
            #
            # ax[1].set_xlabel('Reduced Frequency, k')
            # ax[1].set_ylim([-3.3, 3.3])
            # ax[1].set_yticks(np.linspace(-np.pi, np.pi, 5))
            # ax[1].set_yticklabels(['-$\pi$','-$\pi/2$', '0', '$\pi/2$', '$\pi$'])
            # # ax.set_ylabel('Normalised Response')
            # freqresp_title = 'ROM - %s, r = %g, %s' % (self.algorithm, rstates, display_frequency)
            # ax[0].set_title(freqresp_title)
            # ax[0].legend()
            #
            #
            #
            # # Plot interpolation regions
            # if nfreqs > 1:
            #     for i in range(nfreqs):
            #         if k_rom[i] != 0 and k_rom[i] != np.inf:
            #             index_of_frequency = np.argwhere(kv >= k_rom[i])[0]
            #             ax[0].plot(k_rom[i],
            #                        np.max(np.abs(Y_full_system[0, 0, index_of_frequency])),
            #                        lw=1,
            #                        marker='o',
            #                        color='r')
            #             ax[1].plot(k_rom[i],
            #                        np.max(np.angle(Y_full_system[0, 0, index_of_frequency])),
            #                        lw=1,
            #                        marker='o',
            #                        color='r')
            # else:
            #     if k_rom != 0 and k_rom != np.inf:
            #         index_of_frequency = np.argwhere(kv >= k_rom)[0]
            #         ax[0].plot(k_rom,
            #                    np.max(np.abs(Y_full_system[0, 0, index_of_frequency])),
            #                    lw=1,
            #                    marker='o',
            #                    color='r')
            #         ax[1].plot(k_rom,
            #                    np.max(np.angle(Y_full_system[0, 0, index_of_frequency])),
            #                    lw=1,
            #                    marker='o',
            #                    color='r')
            # fig.show()
            # # fig.savefig('./figs/theo_rolled/Freq_resp%s.eps' % freqresp_title)
            # # fig.savefig('./figs/theo_rolled/Freq_resp%s.png' % freqresp_title)
            #
            # # Relative error
            # fig, ax = plt.subplots()
            #
            # real_rel_error = np.abs(rel_error.real)
            # imag_rel_error = np.abs(rel_error.imag)
            #
            # ax.loglog(kv, real_rel_error,
            #             color='k',
            #             lw=1.5,
            #             label='Real')
            #
            # ax.loglog(kv, imag_rel_error,
            #             ls='--',
            #             color='k',
            #             lw=1.5,
            #             label='Imag')
            #
            # errresp_title = 'ROM - %s, r = %g, %s' % (self.algorithm, rstates, display_frequency)
            # ax.set_title(errresp_title)
            # ax.set_xlabel('Reduced Frequency, k')
            # ax.set_ylabel('Relative Error')
            # ax.set_ylim([1e-5, 1])
            # ax.legend()
            # fig.show()
            #
            # # fig.savefig('./figs/theo_rolled/Err_resp%s.eps' % errresp_title)
            # # fig.savefig('./figs/theo_rolled/Err_resp%s.png' % errresp_title)
        #
        # if return_error:
        #     return kv, rel_error




def evec(j):
    """j-th unit vector (in row format)"""
    e = np.zeros(j+1)
    e[j] = 1
    return e

if __name__ == "__main__":
    pass
