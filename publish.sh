#!/bin/sh -e

: ${CHARM=virtual-accelerator}
: ${CHARM_DIR:=./build/builds/$CHARM}
: ${UPDATE_RESOURCES:=no}

echo "login onto launchpad."
charm login

echo "checking whether the charm looks OK."
charm proof ${CHARM_DIR}

echo "pushing the charm onto cs:~6wind/$CHARM."
charm push ${CHARM_DIR} cs:~6wind/$CHARM

echo "getting latest revision pushed."
charm_rev=$(charm show cs:~6wind/$CHARM revision-info | sed -n 3p | awk '{print $2}')

if [ "$UPDATE_RESOURCES" = "yes" ]; then
	echo "updating resources to upload."
	charm attach ${charm_rev} credentials=${CHARM_DIR}/${CHARM}_resources/6wind-authentication-credentials.deb
	charm attach ${charm_rev} license=${CHARM_DIR}/${CHARM}_resources/va.lic
	charm attach ${charm_rev} custom_fp_conf=${CHARM_DIR}/${CHARM}_resources/custom_fast_path.env
fi

resources_args=
for res in credentials custom_fp_conf license
do
	res_rev=$(charm list-resources ${charm_rev} | grep $res | awk '{print $2}')
	resources_args="${resources_args} --resource ${res}-${res_rev}"
done

echo "releasing the charm latest revision as public."
charm release $charm_rev $resources_args
