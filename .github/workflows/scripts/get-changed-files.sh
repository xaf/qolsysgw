#!/usr/bin/env bash

set -e

# Complain if the BASE_SHA is not set
BASE_SHA=${BASE_SHA:-${GITHUB_BASE_SHA:-HEAD^}}
GITHUB_OUTPUT=${GITHUB_OUTPUT:-/dev/null}

# Make sure to fetch the base sha
if ! git log -1 "${BASE_SHA}" &>/dev/null; then
    echo >&2 "Base sha ${BASE_SHA} not found, fetching from origin"
    if ! git fetch origin "${BASE_SHA}" 2>/dev/null; then
        echo >&2 "Direct fetch failed, attempting to deepen repository"
        depth_increment=100
        max_depth=1000
        curr_depth=$(git rev-list --count HEAD)

        while ! git log -1 "${BASE_SHA}" &>/dev/null; do
            # Check if we've reached the max depth
            if [[ $curr_depth -ge $max_depth ]]; then
                echo >&2 "Reached maximum depth of ${max_depth}"
                break
            fi

            echo >&2 "Deepening repository by ${depth_increment} commits (current depth: ${curr_depth})"
            git fetch --deepen=${depth_increment}

            # Check if we got any new history
            prev_depth=$curr_depth
            curr_depth=$(git rev-list --count HEAD)

            if [[ $curr_depth -eq $prev_depth ]]; then
                echo >&2 "No new history after deepening"
                break
            fi
        done

        if ! git log -1 "${BASE_SHA}" &>/dev/null; then
            echo >&2 "Failed to fetch base sha ${BASE_SHA}"
            exit 1
        fi
    fi
fi

# Function to check if any files matching patterns were modified/changed/deleted
check_patterns() {
    get_files "$@" >/dev/null && echo "true" || echo "false"
}

# Function to check if a value matches a pattern
check_pattern() {
    local value=$1
    local original_pattern=$2
    local patterns=("$original_pattern")

    # If the pattern ends with a slash, it is a directory,
    # and consider the /**-ending pattern
    if [[ "$original_pattern" == */ ]]; then
        patterns+=("$original_pattern**")
    fi

    # If the pattern ends with neither a wildcard, nor a /, add `/**`
    if [[ "$original_pattern" != *'*' && "$original_pattern" != */ ]]; then
        patterns+=("$original_pattern/**")
    fi

    # Now check if any of the patterns match
    local pattern
    for pattern in "${patterns[@]}"; do
        # Use bash's pattern matching
        if [[ "$value" == $pattern ]]; then
            return 0  # Match found
        fi
    done

    return 1  # No match found
}

# Function to get all files matching patterns for a specific status
get_files() {
    local git_command=$1
    shift
    local patterns=("$@")

    # Get all changed files once
    local all_files=$($git_command "${BASE_SHA}" | grep -v '^$')
    all_files=($all_files)

    # Separate exclusion and inclusion patterns
    local include_patterns=()
    local exclude_patterns=()
    local pattern
    for pattern in "${patterns[@]}"; do
        if [[ "${pattern:0:1}" == "!" ]]; then
            # Make it interpret the pattern using eval; this is a bit dangerous
            # but we need to do it to get the correct pattern
            # shellcheck disable=SC2086
            stripped_pattern=($(eval echo "${pattern:1}"))
            exclude_patterns+=("${stripped_pattern[@]}")
        else
            include_patterns+=("$pattern")
        fi
    done

    # Remove all files matching a negative pattern
    for pattern in "${exclude_patterns[@]}"; do
        local keep_files=()
        local file
        for file in "${all_files[@]}"; do
            # Use bash's pattern matching
            check_pattern "$file" "$pattern"
            if ! check_pattern "$file" "$pattern"; then
                keep_files+=("$file")
            fi
        done
        all_files=("${keep_files[@]}")
    done

    # Check if any of the include patterns match
    if [[ ${#include_patterns[@]} -ne 0 ]]; then
        local keep_files=()
        local file
        for file in "${all_files[@]}"; do
            for pattern in "${include_patterns[@]}"; do
                # Use bash's pattern matching
                if check_pattern "$file" "$pattern"; then
                    keep_files+=("$file")
                    break  # Break out of the inner loop if a match is found
                fi
            done
        done
        all_files=("${keep_files[@]}")
    fi

    # Print the list of files that matched, separated by a newline, if any
    if [[ ${#all_files[@]} -gt 0 ]]; then
        printf '%s\n' "${all_files[@]}"
    fi

    # Return 0 if any files matched, 1 otherwise
    if [[ ${#all_files[@]} -gt 0 ]]; then
        return 0
    else
        return 1
    fi
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

    # Read the value from the environment in case it might be multiline
    value=${!varname}

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
    changed_files=$(get_files git_changed "${patterns[@]}" || true)
    modified_files=$(get_files git_modified "${patterns[@]}" || true)
    deleted_files=$(get_files git_deleted "${patterns[@]}" || true)

    # Convert newlines to spaces and set outputs
    echo "${prefix}changed_files=${changed_files//$'\n'/ }" | tee -a "$GITHUB_OUTPUT"
    echo "${prefix}modified_files=${modified_files//$'\n'/ }" | tee -a "$GITHUB_OUTPUT"
    echo "${prefix}deleted_files=${deleted_files//$'\n'/ }" | tee -a "$GITHUB_OUTPUT"
done < <(printenv | sort)
