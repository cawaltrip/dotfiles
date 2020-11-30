set statusline=
set statusline+=%#DiffAdd#%{(mode()=='n')?'\ \ NORMAL\ ':''}
set statusline+=%#DiffText#%{(mode()=='i')?'\ \ INSERT\ ':''}
set statusline+=%#DiffDelete#%{(mode()=='R')?'\ \ RPLACE\ ':''}
set statusline+=%#StatusLineTermNC#%{(mode()=='v')?'\ \ VISUAL\ ':''}
set statusline+=%#StatusLineTerm#%{(mode()=='V')?'\ \ VILINE\ ':''}
set statusline+=%#CursorIM#       " change Color
set statusline+=\ %n\           " buffer number
set statusline+=%#Visual#       " change color
set statusline+=%{&paste?'\ PASTE\ ':''}
set statusline+=%{&spell?'\ SPELL\ ':''}
set statusline+=%#CursorIM#     " change color
set statusline+=%R              " readonly flag
set statusline+=%#Cursor#       " change color
set statusline+=%M              " modified [+] flag
set statusline+=%#CursorLine#   " change color
set statusline+=%<              " Start truncating here if the filename runs long
set statusline+=\ \ %f\         " Path to the file in the buffer
set statusline+=%=              " right align break
set statusline+=%#CursorLineNR# " change color
set statusline+=\ %Y\           " file type
set statusline+=%#CursorIM#     " change color
set statusline+=\ %3l:%-2c\     " line : column
set statusline+=%#Cursor#       " change color
set statusline+=\ %3p%%\        " percentage of file
