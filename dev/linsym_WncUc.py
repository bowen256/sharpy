'''
Analytical linearisation of Wnc matrix.

Sign convention:

Scalar quantities are all lower case, e.g. zeta
Arrays begin with upper case, e.g. Zeta_i
2 D Matrices are all upper case, e.g. AW, ZETA=[Zeta_i]
3 D arrays (tensors) will be labelled with a 3 in the name, e.g. A3

'''

import numpy as np
import sympy as sm
import sympy.tensor.array as smarr
import linfunc


##### Define symbols


### vertices vectors
# coordinates
zeta00_x,zeta00_y,zeta00_z=sm.symbols('zeta00_x,zeta00_y,zeta00_z', real=True)
zeta01_x,zeta01_y,zeta01_z=sm.symbols('zeta01_x,zeta01_y,zeta01_z', real=True)
zeta02_x,zeta02_y,zeta02_z=sm.symbols('zeta02_x,zeta02_y,zeta02_z', real=True)
zeta03_x,zeta03_y,zeta03_z=sm.symbols('zeta03_x,zeta03_y,zeta03_z', real=True)
# vectors
Zeta00,Zeta01,Zeta02,Zeta03=sm.symbols('Zeta00 Zeta01 Zeta02 Zeta03', real=True)
Zeta00=smarr.MutableDenseNDimArray([zeta00_x,zeta00_y,zeta00_z])
Zeta01=smarr.MutableDenseNDimArray([zeta01_x,zeta01_y,zeta01_z])
Zeta02=smarr.MutableDenseNDimArray([zeta02_x,zeta02_y,zeta02_z])
Zeta03=smarr.MutableDenseNDimArray([zeta03_x,zeta03_y,zeta03_z])


### external velocity at nodes - not required here
# coordinates
u00_x,u00_y,u00_z=sm.symbols('u00_x u00_y u00_z', real=True)
u01_x,u01_y,u01_z=sm.symbols('u01_x u01_y u01_z', real=True)
u02_x,u02_y,u02_z=sm.symbols('u02_x u02_y u02_z', real=True)
u03_x,u03_y,u03_z=sm.symbols('u03_x u03_y u03_z', real=True)
# vectors
U00,U01,U02,U03=sm.symbols('U00 U01 U02 U03', real=True)
U01=smarr.MutableDenseNDimArray([u00_x,u00_y,u00_z])
U02=smarr.MutableDenseNDimArray([u01_x,u01_y,u01_z])
U03=smarr.MutableDenseNDimArray([u02_x,u02_y,u02_z])
U04=smarr.MutableDenseNDimArray([u03_x,u03_y,u03_z])


### velocity at collocation point
uc_x, uc_y, uc_z=sm.symbols('uc_x uc_y uc_z', real=True)
Uc=smarr.MutableDenseNDimArray([uc_x,uc_y,uc_z])


### Compute normal to panel
# see surface.AeroGridSurface.get_panel_normal
R02=Zeta02-Zeta00
R13=Zeta03-Zeta01
Norm=linfunc.cross_product(R02,R13)
Norm=Norm/linfunc.norm2(Norm)
### check norm
assert linfunc.scalar_product(Norm,R02).simplify()==0, 'Norm is wrong'
assert linfunc.scalar_product(Norm,R13).simplify()==0, 'Norm is wrong'
assert linfunc.scalar_product(Norm,Norm).simplify()==1, 'Normal is not unit length'


### Compute normal velocity at panel
Unorm=linfunc.scalar_product(Norm,Uc)
Unorm=sm.simplify(Unorm)

### Compute derivative
dUnorm_dZeta=sm.derive_by_array(Unorm,[Zeta00,Zeta01,Zeta02,Zeta03])
#dUnorm_dZeta=linfunc.simplify(dUnorm_dZeta)



################################################################################
### exploit combined derivatives
################################################################################


dR_dZeta=sm.derive_by_array([R02,R13],[Zeta00,Zeta01,Zeta02,Zeta03])


### redefine R02,R13
r02_x,r02_y,r02_z=sm.symbols('r02_x r02_y r02_z', real=True)
r13_x,r13_y,r13_z=sm.symbols('r13_x r13_y r13_z', real=True)
R02=smarr.MutableDenseNDimArray([r02_x,r02_y,r02_z])
R13=smarr.MutableDenseNDimArray([r13_x,r13_y,r13_z])

Norm=linfunc.cross_product(R02,R13)
Norm=Norm/linfunc.norm2(Norm)
### check norm
assert linfunc.scalar_product(Norm,R02).simplify()==0, 'Norm is wrong'
assert linfunc.scalar_product(Norm,R13).simplify()==0, 'Norm is wrong'
assert linfunc.scalar_product(Norm,Norm).simplify()==1, 'Normal is not unit length'
### Compute normal velocity at panel
Unorm=linfunc.scalar_product(Norm,Uc)
Unorm=sm.simplify(Unorm)
# derivative
dUnorm_dR=sm.derive_by_array(Unorm,[R02,R13])




