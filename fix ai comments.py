def remove_blank_lines(input_file, output_file):
    # Read with error handling - replaces problematic characters with '?'
    with open(input_file, 'r', encoding='utf-8', errors='replace') as infile:
        lines = infile.readlines()
    
    modified_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not '"' in stripped:
            # Capitalize the first letter of the comment
            # Find the first alphabetic character after the '#'
            comment_content = stripped[1:].lstrip()
            if comment_content:
                # Capitalize the first letter of the comment content
                capitalized_content = comment_content[0:].capitalize()
                # Change a few words to fix spelling
                capitalized_content = capitalized_content.replace("Ocr", "OCR")
                capitalized_content = capitalized_content.replace("Macos", "macOS")
                capitalized_content = capitalized_content.replace("Mss", "MSS")
                capitalized_content = capitalized_content.replace("Gui", "GUI")
                if capitalized_content.startswith("-") and capitalized_content.endswith("-"):
                    capitalized_content = capitalized_content.replace("-", "")
                if capitalized_content.startswith("=") or capitalized_content.endswith("="):
                    capitalized_content = capitalized_content.replace("=", "")
                # Preserve the original indentation and '#'
                indentation = line[:len(line) - len(line.lstrip())]
                modified_lines.append(f"{indentation}# {capitalized_content}\n")
            else:
                modified_lines.append(line)
        else:
            modified_lines.append(line)
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.writelines(modified_lines)

# Usage
input_py = input("Input file: ")
output_py = input("Output file: ")

remove_blank_lines(input_py, output_py)
print(f"Comments processed in {input_py} and saved to {output_py}.")