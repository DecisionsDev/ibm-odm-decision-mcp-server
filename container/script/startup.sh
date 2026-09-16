#!/usr/bin/env bash
set -e
[ "${LOG_LEVEL}" = "DEBUG" ] && set -x

AUTHOIDC_DIR="${AUTHOIDC_DIR:-/authOidc}"
XML_FILE="${AUTHOIDC_DIR}/openIdWebSecurity.xml"
PROPS_FILE="${AUTHOIDC_DIR}/openIdParameters.properties"

# Only proceed if the directory exists and contains at least one of the two files
if [ -d "${AUTHOIDC_DIR}" ] && { [ -f "${XML_FILE}" ] || [ -f "${PROPS_FILE}" ]; }; then

    # Maps: ENV_VAR_NAME -> xml_attribute_name -> properties_key
    declare -A XML_ATTR=(
        [CLIENT_ID]="clientId"
        [CLIENT_SECRET]="clientSecret"
        [TOKEN_URL]="tokenEndpointUrl"
        [SCOPE]="scope"
         [PKJWT_KEY_PATH]="keyAliasName"
        [PKJWT_CERT_PATH]="keyAliasName"

    )
    declare -A PROPS_KEY=(
        [CLIENT_ID]="OPENID_CLIENT_ID"
        [CLIENT_SECRET]="OPENID_CLIENT_SECRET"
        [TOKEN_URL]="OPENID_TOKEN_URL"
        [SCOPE]="OPENID_SCOPE"
         [PKJWT_KEY_PATH]="OPENID_CLIENT_ASSERTION_ALIAS_NAME"
        [PKJWT_CERT_PATH]="OPENID_CLIENT_ASSERTION_ALIAS_NAME"
    )
    # Maps: ENV_VAR_NAME -> value prefix/suffix to wrap around the extracted value
    declare -A VALUE_PREFIX=(
         [PKJWT_KEY_PATH]="/mcp-certs/private-keys/"
        [PKJWT_CERT_PATH]="/mcp-certs/private-keys/"
    )
    declare -A VALUE_SUFFIX=(
         [PKJWT_KEY_PATH]="/tls.key"
        [PKJWT_CERT_PATH]="/tls.crt"
    )

    # Snapshot which PKJWT vars were already set before the loop (pre-set env vars must not be file-checked)
     PKJWT_KEY_PATH_PRESET="${PKJWT_KEY_PATH}"
    PKJWT_CERT_PATH_PRESET="${PKJWT_CERT_PATH}"

    # Build list of files being parsed for the startup message
    PARSING_FILES=""
    [ -f "${XML_FILE}" ]   && PARSING_FILES="${XML_FILE}"
    [ -f "${PROPS_FILE}" ] && PARSING_FILES="${PARSING_FILES:+${PARSING_FILES} and }${PROPS_FILE}"
    echo "[startup] Parsing ${PARSING_FILES}"

    # Extract any variables defined in the XML file
    declare -A XML_VARS=()
    if [ -f "${XML_FILE}" ]; then
        VAR_COUNT=$(xmllint --xpath "count(//*[local-name()='variable'])" "${XML_FILE}" 2>/dev/null || echo 0)
        if [[ "${VAR_COUNT}" =~ ^[0-9]+$ ]]; then
            for ((i=1; i<=VAR_COUNT; i++)); do
                V_NAME=$(xmllint --xpath "string((//*[local-name()='variable'])[${i}]/@name)" "${XML_FILE}" 2>/dev/null)
                V_VAL=$(xmllint --xpath "string((//*[local-name()='variable'])[${i}]/@value)" "${XML_FILE}" 2>/dev/null)
                if [ -n "${V_NAME}" ]; then
                    for EXISTING_VAR in "${!XML_VARS[@]}"; do
                        V_VAL="${V_VAL//\$\{$EXISTING_VAR\}/${XML_VARS[$EXISTING_VAR]}}"
                    done
                    XML_VARS["${V_NAME}"]="${V_VAL}"
                fi
            done
        fi
    fi

    for VAR in CLIENT_ID CLIENT_SECRET TOKEN_URL SCOPE PKJWT_KEY_PATH PKJWT_CERT_PATH; do
        # Skip if already set
        if [ -n "${!VAR}" ]; then
            if [ "${VAR}" = "CLIENT_SECRET" ]; then
                SAFE_VALUE="${!VAR:0:1}*****${!VAR: -1}"
            else
                SAFE_VALUE="${!VAR}"
            fi
            echo "[startup] ${VAR}=${SAFE_VALUE} (defined as environment variable)."
            continue
        fi

        VALUE=""
        SOURCE=""

        # Try XML file first (exclude commented-out lines)
        if [ -f "${XML_FILE}" ]; then
            if [ "${VAR}" = "PKJWT_KEY_PATH" ] || [ "${VAR}" = "PKJWT_CERT_PATH" ]; then
                # Extract keyAliasName from openidConnectClient elements where tokenEndpointAuthMethod is set to "private_key_jwt"
                VALUE=$(xmllint --xpath "string((//*[local-name()='openidConnectClient'][@tokenEndpointAuthMethod='private_key_jwt'])[1]/@keyAliasName)" "${XML_FILE}" 2>/dev/null)
            elif [ -n "${XML_ATTR[$VAR]:-}" ]; then
                VALUE=$(xmllint --xpath "string((//*[local-name()='openidConnectClient'])[1]/@${XML_ATTR[$VAR]})" "${XML_FILE}" 2>/dev/null)
            fi
            if [ -n "${VALUE}" ]; then
                # Replace any variable references in the value
                for V_NAME in "${!XML_VARS[@]}"; do
                    VALUE="${VALUE//\$\{$V_NAME\}/${XML_VARS[$V_NAME]}}"
                done
            fi
            SOURCE="${XML_FILE}"
        fi

        # Fallback to properties file
        if [ -z "${VALUE}" ] && [ -f "${PROPS_FILE}" ]; then
            VALUE=$(sed -n "s/^${PROPS_KEY[$VAR]}=\([^# ]*\).*/\1/p" "${PROPS_FILE}" | head -1)
            SOURCE="${PROPS_FILE}"
        fi

        if [ -n "${VALUE}" ]; then
            # Apply value prefix/suffix if defined for this variable
            if [ -n "${VALUE_PREFIX[$VAR]:-}" ]; then
                VALUE="${VALUE_PREFIX[$VAR]}${VALUE}"
            fi
            if [ -n "${VALUE_SUFFIX[$VAR]:-}" ]; then
                VALUE="${VALUE}${VALUE_SUFFIX[$VAR]}"
            fi
            export "${VAR}=${VALUE}"

            if [ "${VAR}" = "CLIENT_SECRET" ]; then
                SAFE_VALUE="${VALUE:0:1}*****${VALUE: -1}"
            else
                SAFE_VALUE="${VALUE}"
            fi

            echo "[startup] ${VAR}=${SAFE_VALUE} (set from ${SOURCE})."
        else
            echo "[startup] ${VAR} not found in config files, leaving unset."
        fi
    done

    # Verify that the PKJWT key and cert files exist (only when derived by this script, not pre-set).
    # Unset both if either derived file is missing.
    if [ -z "${PKJWT_KEY_PATH_PRESET}" ] || [ -z "${PKJWT_CERT_PATH_PRESET}" ]; then
        MISSING=""
        [ -n "${PKJWT_KEY_PATH}"  ] && [ ! -f "${PKJWT_KEY_PATH}"  ] && MISSING="${PKJWT_KEY_PATH}"
        [ -n "${PKJWT_CERT_PATH}" ] && [ ! -f "${PKJWT_CERT_PATH}" ] && MISSING="${MISSING:+${MISSING}, }${PKJWT_CERT_PATH}"
        if [ -n "${MISSING}" ]; then
            echo "[startup] WARNING: PKJWT_KEY_PATH and PKJWT_CERT_PATH unset because file(s) not found: ${MISSING}."
            unset PKJWT_KEY_PATH
            unset PKJWT_CERT_PATH
        fi
    fi

fi

exec ibm-odm-decision-mcp-server "$@"
