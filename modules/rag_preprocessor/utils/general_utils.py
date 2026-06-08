def expand_prompts_with_info(prompts_dict, prompt_info_list):
        info_by_id = {item['prompt_uuid']: item for item in prompt_info_list}
        
        result = {}
        for nombre, id_prompt in prompts_dict.items():
            if id_prompt is None:
                result[nombre] = None
            else:
                info = info_by_id.get(id_prompt)
                if info:
                    result[nombre] = {
                        "text": info["text"],
                        "variables": info["variables"]
                    }
                else:
                    result[nombre] = None

        return result