import os

html_path = r"c:\Projects\Error404_POS\Error404\sales\templates\manager.html"
with open(html_path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Header Actions
text = text.replace(
    'class="appearance-none w-full bg-white border-2 border-slate-200 rounded-2xl py-2.5 md:py-4',
    'class="appearance-none w-full bg-white border-2 border-slate-200 rounded-2xl md:rounded-3xl py-3 md:py-4 text-xs md:text-sm'
)

btns_old = '''<a href="{% url 'add_product' %}" class="flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-[800] px-4 py-2.5 md:px-8 md:py-4 rounded-2xl transition-all shadow-[4px_4px_0px_0px_rgba(203,213,225,1)] active:translate-y-[2px] active:shadow-none uppercase tracking-widest text-[9px] md:text-[10px] border-2 border-orange-500 w-full sm:w-auto">
                        <i class="bi bi-plus-lg text-lg"></i>
                        <span>Add New Drink</span>
                    </a>
                    <a href="{% url 'generate_daily_report' %}" target="_blank" class="flex items-center justify-center gap-2 bg-blue-500 hover:bg-blue-600 text-white font-[800] px-4 py-2.5 md:px-8 md:py-4 rounded-2xl transition-all shadow-[4px_4px_0px_0px_rgba(203,213,225,1)] active:translate-y-[2px] active:shadow-none uppercase tracking-widest text-[9px] md:text-[10px] border-2 border-blue-500 w-full sm:w-auto">
                        <i class="bi bi-file-earmark-pdf text-lg"></i> Daily Report
                    </a>'''
btns_new = '''<div class="grid grid-cols-2 gap-2 w-full sm:w-auto sm:flex sm:gap-3">
                        <a href="{% url 'add_product' %}" class="flex-1 sm:flex-none flex items-center justify-center gap-1.5 md:gap-2 bg-orange-500 hover:bg-orange-600 text-white font-[800] px-3 md:px-8 py-3.5 md:py-4 rounded-2xl md:rounded-3xl transition-all shadow-sm md:shadow-[4px_4px_0px_0px_rgba(203,213,225,1)] active:translate-y-[2px] active:shadow-none uppercase tracking-widest text-[9px] md:text-[10px] border-2 border-orange-500 min-w-0">
                            <i class="bi bi-plus-lg text-sm md:text-lg"></i>
                            <span class="truncate hidden min-[360px]:inline">Add Drink</span>
                            <span class="truncate min-[360px]:hidden">Add</span>
                        </a>
                        <a href="{% url 'generate_daily_report' %}" target="_blank" class="flex-1 sm:flex-none flex items-center justify-center gap-1.5 md:gap-2 bg-blue-500 hover:bg-blue-600 text-white font-[800] px-3 md:px-8 py-3.5 md:py-4 rounded-2xl md:rounded-3xl transition-all shadow-sm md:shadow-[4px_4px_0px_0px_rgba(203,213,225,1)] active:translate-y-[2px] active:shadow-none uppercase tracking-widest text-[9px] md:text-[10px] border-2 border-blue-500 min-w-0">
                            <i class="bi bi-file-earmark-pdf text-sm md:text-lg"></i>
                            <span class="truncate hidden min-[360px]:inline">Daily Report</span>
                            <span class="truncate min-[360px]:hidden">Report</span>
                        </a>
                    </div>'''
text = text.replace(btns_old, btns_new)

# 2. Bento Stat Cards
text = text.replace('class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 md:gap-6"', 'class="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 md:gap-6"')
text = text.replace('p-4 md:p-6 rounded-[2rem] md:rounded-[2.5rem]', 'p-4 md:p-6 rounded-[1.5rem] md:rounded-[2.5rem]')
text = text.replace('p-4 md:p-5 rounded-[2rem] md:rounded-[2.5rem]', 'p-4 md:p-5 rounded-[1.5rem] md:rounded-[2.5rem]')
text = text.replace('text-[9px] font-[800] text-slate-400 uppercase tracking-widest text-right leading-tight', 'text-[8px] md:text-[9px] font-[800] text-slate-400 uppercase tracking-widest text-right leading-tight max-w-[70%]')
text = text.replace('class="text-3xl font-[800]', 'class="text-2xl md:text-3xl font-[800]')
text = text.replace('class="text-xl font-[900]', 'class="text-lg md:text-2xl font-[900]')
text = text.replace('Annual Tax in Income.', 'Annual Tax')

# 3. Raw Materials
text = text.replace('p-6 md:p-8 mb-6', 'p-5 md:p-8 mb-6')
text = text.replace('p-4 md:p-5 bg-slate-50 rounded-2xl', 'p-3 md:p-5 bg-slate-50 rounded-[1.5rem]')
text = text.replace('p-5 bg-slate-50 rounded-2xl', 'p-3 md:p-5 bg-slate-50 rounded-[1.5rem]')
text = text.replace('text-[10px] font-[800] tracking-widest uppercase truncate', 'text-[8px] md:text-[10px] font-[800] tracking-widest uppercase truncate')
text = text.replace('text-2xl font-[800] text-slate-900', 'text-xl md:text-2xl font-[800] text-slate-900')
text = text.replace('h-2 rounded-full mt-3', 'h-[6px] md:h-2 rounded-full mt-2 md:mt-3')

# 4. Table Header & Sticky column
text = text.replace('border-b-2 border-slate-50 bg-white/50 flex flex-col md:flex-row gap-4', 'border-b-2 border-slate-50 bg-white/50 flex flex-col md:flex-row gap-3 md:gap-4')
text = text.replace('min-w-[1100px]', 'min-w-[1050px]')
text = text.replace('class="px-8 py-5 text-[10px]', 'class="px-4 md:px-8 py-3 md:py-5 text-[10px]')
text = text.replace('class="px-8 py-5 text-center"', 'class="px-4 md:px-8 py-3 md:py-5 text-center"')
text = text.replace('class="px-8 py-5 text-right"', 'class="px-4 md:px-8 py-3 md:py-5 text-right"')
text = text.replace('class="px-8 py-5"', 'class="px-4 md:px-8 py-3 md:py-5"')
text = text.replace('px-8 py-5', 'px-4 md:px-8 py-3 md:py-5')

text = text.replace(
    'class="px-4 md:px-8 py-3 md:py-5 text-[10px] font-[800] text-slate-400 uppercase tracking-widest">product Details</th>',
    'class="px-4 md:px-8 py-3 md:py-5 text-[10px] font-[800] text-slate-400 uppercase tracking-widest sticky left-0 bg-slate-50/95 backdrop-blur-md z-20 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.1)]">product Details</th>'
)

text = text.replace(
    '<td class="px-2 py-1">\\n                                    <div class="flex items-center gap-5">',
    '<td class="px-2 md:px-4 py-2 sticky left-0 bg-white group-hover:bg-slate-50 transition-colors z-10 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.05)] border-r border-slate-50">\\n                                    <div class="flex items-center gap-3 md:gap-5">'
)

text = text.replace(
    '<td class="px-2 py-1">\\n                        <div class="flex items-center gap-5">',
    '<td class="px-2 md:px-4 py-2 sticky left-0 bg-white z-10 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.05)] border-r border-slate-50">\\n                        <div class="flex items-center gap-3 md:gap-5">'
)

# 5. Modals
text = text.replace('bg-white w-full max-w-md rounded-[2.5rem] p-8 border-2', 'bg-white w-full max-w-md rounded-[2rem] md:rounded-[2.5rem] p-6 md:p-8 border-2')
text = text.replace('max-w-sm w-full p-8 text-center', 'max-w-sm w-full p-6 md:p-8 text-center')

with open(html_path, "w", encoding="utf-8") as f:
    f.write(text)

print("done")
