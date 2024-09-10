from typing import Optional
import streamlit as st
from pydantic import BaseModel
import pandas as pd

# import streamlit_pydantic as sp


# class ExampleModel(BaseModel):
#     some_text: str
#     some_number: int
#     some_boolean: bool


st.title('Hello World')

# data = sp.pydantic_form(key="my_form", model=ExampleModel)
# if data:
#     st.json(data.model_dump_json())

# Initialize session_state if it doesn't exist
if 'dictionaries' not in st.session_state:
    st.session_state['dictionaries'] = []

name = st.text_input('Enter your name', placeholder='Type here...')
age = st.number_input('Enter your age', 0, 100, placeholder='0')

if st.button('Add Dictionary'):
    new_dictionary = {
        'name': name,
        'age': age,
    }
    if new_dictionary not in st.session_state['dictionaries']:
        st.session_state['dictionaries'].append(new_dictionary)
        st.success('Dictionary added successfully.')
    else:
        st.warning('Dictionary already exists.')

# st.write('All Dictionaries:', st.session_state['dictionaries'])
st.json(st.session_state['dictionaries'], expanded=False)

# # show the first dictionary, if one exists
# hi = None
# if st.session_state['dictionaries']:
#     hi = st.session_state['dictionaries'][0]
#     # st.write('First Dictionary:', st.session_state['dictionaries'][0])
# hi

df = pd.DataFrame(st.session_state['dictionaries'])
df
