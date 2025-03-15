#!/usr/bin/env bash

set -e

# Complain if the BASE_SHA is not set
BASE_SHA=${BASE_SHA:-${GITHUB_BASE_SHA:-HEAD^}}
GITHUB_OUTPUT=${GITHUB_OUTPUT:-/dev/null}

# Make sure to fetch the base sha
if ! git log -1 "${BASE_SHA}" &>/dev/null; then
    echo >&2 "Base sha ${BASE_SHA} not found, fetching from origin"
    git fetch origin "${BASE_SHA}"
fi

# Function to check if any files matching patterns were modified/changed/deleted
check_patterns() {
    local result=false
    local patterns=("$@")
    local git_command=$1
    shift

    for pattern in "${patterns[@]}"; do
        if $git_command "${BASE_SHA}" | grep -q "^${pattern}"; then
            result=true
            break
        fi
    done

    echo "$result"
}

# Function to get all files matching patterns for a specific status
get_files() {
    local patterns=("$@")
    local git_command=$1
    shift

    for pattern in "${patterns[@]}"; do
        $git_command "${BASE_SHA}" | grep "^${pattern}" || true
    done
}

# Git commands for different file states
git_changed() {
    git diff --name-only --diff-filter=ACMR "$@"
}

git_modified() {
    git diff --name-only --diff-filter=ACMRD "$@"
}

git_deleted() {
    git diff --name-only --diff-filter=D "$@"
}

# Find all env variables in the format MODIFIED_FILES_<category>
while IFS= read -r var; do
    if [[ "$var" != "MODIFIED_FILES="* ]] && [[ "$var" != "MODIFIED_FILES_"* ]]; then
        continue
    fi

    # Split the variable name and the value
    varname=${var%=*}
    value=${var#*=}

    # Get the category from the variable name
    category=$(echo "$varname" | cut -d'_' -f3-)
    category=${category,,}
    prefix=${category:+${category}_}

    # Get the patterns from the value
    patterns=($value)

    # Check for modifications and set outputs
    echo "${prefix}any_changed=$(check_patterns git_changed "${patterns[@]}")" | tee -a "$GITHUB_OUTPUT"
    echo "${prefix}any_modified=$(check_patterns git_modified "${patterns[@]}")" | tee -a "$GITHUB_OUTPUT"
    echo "${prefix}any_deleted=$(check_patterns git_deleted "${patterns[@]}")" | tee -a "$GITHUB_OUTPUT"

    # Get all files for each status for logging
    changed_files=$(get_files git_changed "${patterns[@]}")
    modified_files=$(get_files git_modified "${patterns[@]}")
    deleted_files=$(get_files git_deleted "${patterns[@]}")

    # Convert newlines to spaces and set outputs
    echo "${prefix}changed_files=${changed_files//$'\n'/ }" | tee -a "$GITHUB_OUTPUT"
    echo "${prefix}modified_files=${modified_files//$'\n'/ }" | tee -a "$GITHUB_OUTPUT"
    echo "${prefix}deleted_files=${deleted_files//$'\n'/ }" | tee -a "$GITHUB_OUTPUT"
done < <(printenv | sort)
