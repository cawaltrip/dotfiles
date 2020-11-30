"----- Custom Keys -----"
""change the Leader from the default \
let mapleader = " "

"drop to the command shell, get the date and time
"nnoremap <Leader>t m`:r !date /t<Enter>
"" Clear the search register
nnoremap <Leader>/ :let @/ = ""<Enter>

" Using suggestion from Help file for navigation mapping square brackets
" (motions.txt -> sections)
:map [[ ?{<CR>w99[{
:map ][ /}<CR>b99]}
:map ]] j0[[%/{<CR>
:map [] k$][%?}<CR>

" create blank line below current, go back to normal mode
nnoremap <Leader>o o<Esc>
" create blank line above current, go back to normal mode
nnoremap <Leader>O O<Esc>j



" Markdown shortcuts
" Create Italic line
nnoremap <Leader>_ mb^i_<Esc>A_<Esc>`b
nnoremap <Leader>) mb^i_<Esc>A_<Esc>`b
" Create Bold line
nnoremap <Leader>* mb^i__<Esc>A__<Esc>`b
nnoremap <Leader>8 mb^i__<Esc>A__<Esc>`b
" Remove Bold/Italics line
nnoremap <Leader>- mb$F*x0f*x`b


" "Create checkbox (copy to Register c for macro use)
nnoremap <Leader>c mx^i+ [ ] <Esc>`x6l
" "Remove checkbox
nnoremap <Leader>C mx0f+6x<Esc>`x6h
" "Fill the checkbox with an x
nnoremap <Leader>x mx0f[lrx<Esc>`x
" "Clear the checkbox
nnoremap <Leader>X mx0f[lr<Space><Esc>`x


" Create Block Quote
nnoremap <Leader>q mx0i> <Esc>`x
" Delete Block Quote
nnoremap <Leader>Q mx02x<Esc>`x
